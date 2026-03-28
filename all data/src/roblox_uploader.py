#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import time
import re
import sys
import random
import argparse
import logging
import threading

try:
    import requests
except ImportError:
    print("ERROR: 'requests' not installed.  Run:  pip install requests")
    sys.exit(1)

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import RLock, Event

try:
    from tqdm import tqdm
except ImportError:
    # Lightweight fallback when tqdm is missing
    def tqdm(iterable, **kw):
        desc = kw.get("desc", "")
        total = kw.get("total", None)
        for i, item in enumerate(iterable, 1):
            if total:
                print(f"\r{desc}: {i}/{total}", end="", flush=True)
            yield item
        if total:
            print()

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv():
        pass

load_dotenv()

# -- Config ----------------------------------------------------

def _safe_int(val, default=0):
    """Convert to int without crashing on empty strings or garbage."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def _clean_cookie(raw):
    """Strip the '.ROBLOSECURITY=' prefix users may paste from devtools."""
    if not raw:
        return None
    if raw.startswith(".ROBLOSECURITY="):
        raw = raw[len(".ROBLOSECURITY="):]
    return raw or None

API_KEY = os.getenv("ROBLOX_API_KEY") or None
USER_ID = _safe_int(os.getenv("ROBLOX_USER_ID"), 0)
WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL") or None
ROBLOSECURITY = _clean_cookie(os.getenv("ROBLOSECURITY"))

UPLOAD_URL = "https://apis.roblox.com/assets/v1/assets"
OPERATIONS_URL = "https://apis.roblox.com/assets/v1"
ASSET_DELIVERY_URL = "https://assetdelivery.roblox.com/v1/asset"

# Absolute base directory (parent of src/) -- makes paths work
# regardless of what directory the script is launched from.
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_BASE_DIR = (
    os.path.dirname(_SCRIPT_DIR)
    if os.path.basename(_SCRIPT_DIR) == "src"
    else _SCRIPT_DIR
)

RUNS_DIR = os.path.join(_BASE_DIR, "runs")

# -- Defaults (overridable via CLI) ----------------------------
DEFAULT_WORKERS = 2
DEFAULT_TEX_WORKERS = 8
DEFAULT_CDN_WARMUP = 60
DEFAULT_MOD_LIMIT = 1

MIN_DELAY = 0.7
MAX_DELAY = 1.4
RATE_LIMIT_COOLDOWN = 60
MAX_RATE_LIMIT_RETRIES = 3
OP_POLL_ATTEMPTS = 30
OP_POLL_INTERVAL = 2
TEXTURE_FETCH_RETRIES = 4
TEXTURE_FETCH_DELAY = 3

# -- Live upload watch ----------------------------------------
WATCH_TIMEOUT = 30

# RLock (reentrant) so save_mapping can be called while the
# lock is already held by the same thread -- avoids deadlocks.
lock = RLock()
log = logging.getLogger("uploader")

# -- Result types ---------------------------------------------

RESULT_OK = "ok"
RESULT_MODERATED = "moderated"
RESULT_PRE_FAIL = "pre_fail"
RESULT_POST_FAIL = "post_fail"
RESULT_ABORTED = "aborted"
RESULT_RATE_FAIL = "rate_fail"

# -- Shared state (all threads) -------------------------------

moderation_count = 0
moderation_limit = DEFAULT_MOD_LIMIT
abort_event = Event()
moderated_frames: list = []
ghost_risk_frames: list = []


# -- Rate limiter ---------------------------------------------

class _RateLimiter:
    """Thread-safe rate limiter -- enforces a minimum gap between calls."""

    def __init__(self, calls_per_second: float = 1.8):
        self._interval = 1.0 / calls_per_second
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            now = time.time()
            gap = self._interval - (now - self._last)
            if gap > 0:
                time.sleep(gap)
            self._last = time.time()


def record_moderation(filename):
    global moderation_count
    should_notify = False
    with lock:
        moderation_count += 1
        moderated_frames.append(filename)
        count = moderation_count
        if count >= moderation_limit and not abort_event.is_set():
            abort_event.set()
            should_notify = True

    if should_notify:
        msg = (
            f"[!] MODERATION DETECTED -- {filename} flagged. "
            f"Upload stopped to protect your account."
        )
        log.critical(msg)
        notify(msg)


def record_ghost_risk(filename):
    with lock:
        if filename not in ghost_risk_frames:
            ghost_risk_frames.append(filename)


def reset_moderation_state():
    global moderation_count, moderated_frames, ghost_risk_frames
    moderation_count = 0
    moderated_frames = []
    ghost_risk_frames = []
    abort_event.clear()


# -- Discord ---------------------------------------------------

def notify(msg):
    if not WEBHOOK_URL:
        return
    try:
        requests.post(WEBHOOK_URL, json={"content": msg}, timeout=5)
    except Exception:
        log.debug("Discord notification failed")


# -- Run-scoped file helpers -----------------------------------

def _run_dir(run_id):
    return os.path.join(RUNS_DIR, run_id)

def _ensure_run_dir(run_id):
    os.makedirs(_run_dir(run_id), exist_ok=True)

def _mapping_path(run_id):
    return os.path.join(_run_dir(run_id), "mapping.json")

def _output_path(run_id):
    return os.path.join(_run_dir(run_id), "assets.txt")

def load_mapping(run_id):
    path = _mapping_path(run_id)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            log.warning("Corrupt mapping file -- starting fresh")
    return {}

def save_mapping(run_id, data):
    _ensure_run_dir(run_id)
    with lock:
        with open(_mapping_path(run_id), "w") as f:
            json.dump(data, f, indent=4)


# -- Roblox API ------------------------------------------------

def upload_frame(filepath, filename, run_id, retries=0):
    """Upload a single frame. Returns (operation_path, result_type)."""
    if abort_event.is_set():
        return None, RESULT_ABORTED

    frame_number = re.sub(r"\D", "", filename)

    request_body = {
        "assetType": "Decal",
        "displayName": f"{run_id}_Frame_{frame_number}",
        "description": run_id,
        "creationContext": {
            "creator": {"userId": USER_ID},
        },
    }

    headers = {"x-api-key": API_KEY}

    if abort_event.is_set():
        return None, RESULT_ABORTED

    try:
        with open(filepath, "rb") as f:
            res = requests.post(
                UPLOAD_URL,
                headers=headers,
                files={"fileContent": f},
                data={"request": json.dumps(request_body)},
                timeout=30,
            )
    except requests.ConnectionError as exc:
        log.error("Connection error uploading %s (pre-send): %s", filename, exc)
        return None, RESULT_PRE_FAIL
    except requests.Timeout as exc:
        log.error("Timeout uploading %s (data may have been sent): %s", filename, exc)
        record_ghost_risk(filename)
        return None, RESULT_POST_FAIL
    except requests.RequestException as exc:
        log.error("Request error uploading %s: %s", filename, exc)
        record_ghost_risk(filename)
        return None, RESULT_POST_FAIL

    if res.status_code == 403:
        log.warning("[!] MODERATED: %s -- skipping (not retrying)", filename)
        record_moderation(filename)
        return None, RESULT_MODERATED

    if res.status_code == 429:
        if retries >= MAX_RATE_LIMIT_RETRIES:
            log.error("Rate-limited too many times on %s, giving up", filename)
            return None, RESULT_RATE_FAIL
        log.warning(
            "Rate-limited on %s -- waiting %ds (retry %d/%d)",
            filename, RATE_LIMIT_COOLDOWN, retries + 1, MAX_RATE_LIMIT_RETRIES,
        )
        time.sleep(RATE_LIMIT_COOLDOWN)
        return upload_frame(filepath, filename, run_id, retries + 1)

    if res.status_code != 200:
        log.error("Upload failed for %s: %d %s", filename, res.status_code, res.text[:200])
        record_ghost_risk(filename)
        return None, RESULT_POST_FAIL

    path = res.json().get("path")
    if not path:
        log.warning("Got 200 but no operation path for %s -- ghost risk", filename)
        record_ghost_risk(filename)
        return None, RESULT_POST_FAIL

    return path, RESULT_OK


def poll_operation(operation_path):
    """Poll an operation until it resolves to a decal asset ID."""
    headers = {"x-api-key": API_KEY}
    url = f"{OPERATIONS_URL}/{operation_path}"

    for _ in range(OP_POLL_ATTEMPTS):
        try:
            res = requests.get(url, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                if data.get("done"):
                    return data.get("response", {}).get("assetId")
        except requests.RequestException:
            pass
        time.sleep(OP_POLL_INTERVAL)

    return None


class CookieInvalidError(Exception):
    """Raised when the .ROBLOSECURITY cookie is rejected (401/403)."""


def validate_cookie():
    """Quick check: hit the authenticated user endpoint and return True if
    the cookie is still valid.  Returns False on auth failure."""
    if not ROBLOSECURITY:
        return False
    try:
        res = requests.get(
            "https://users.roblox.com/v1/users/authenticated",
            cookies={".ROBLOSECURITY": ROBLOSECURITY},
            timeout=10,
        )
        return res.status_code == 200
    except requests.RequestException:
        return False


def fetch_texture_id(decal_id):
    """Given a decal asset ID, fetch the underlying texture/image ID.

    Raises CookieInvalidError on HTTP 401 (authentication failure —
    cookie expired/invalid).  HTTP 403 is treated as "this specific asset
    is unavailable" (e.g. the uploading account was banned and Roblox
    removed the decal) and simply returns None after retries.
    """
    cookies = {".ROBLOSECURITY": ROBLOSECURITY} if ROBLOSECURITY else {}

    for attempt in range(1, TEXTURE_FETCH_RETRIES + 1):
        try:
            res = requests.get(
                ASSET_DELIVERY_URL,
                params={"id": decal_id},
                cookies=cookies,
                timeout=10,
                allow_redirects=True,
            )

            log.debug(
                "Texture fetch for decal %s (attempt %d): status=%d len=%d snippet=%.200s",
                decal_id, attempt, res.status_code, len(res.text), res.text[:200],
            )

            # 401 = authentication failure — cookie is dead.
            if res.status_code == 401:
                raise CookieInvalidError(
                    f"Cookie rejected (HTTP 401) while fetching "
                    f"texture for decal {decal_id}"
                )

            # 403 = asset unavailable (moderated / removed).
            # Don't retry — the asset won't come back.
            if res.status_code == 403:
                log.warning(
                    "Decal %s returned 403 — asset likely removed/moderated",
                    decal_id,
                )
                return None

            match = re.search(r"<url>[^<]*?id=(\d+)[^<]*</url>", res.text)
            if not match:
                match = re.search(r"id=(\d+)", res.text)

            if match:
                texture_id = match.group(1)
                if texture_id != str(decal_id):
                    return texture_id
                log.debug("Only found decal ID back, not texture -- retrying")

        except CookieInvalidError:
            raise  # always propagate auth failures immediately
        except requests.RequestException as exc:
            log.debug("Texture fetch error for decal %s (attempt %d): %s", decal_id, attempt, exc)

        if attempt < TEXTURE_FETCH_RETRIES:
            time.sleep(TEXTURE_FETCH_DELAY)

    log.warning("Could not resolve texture for decal %s after %d attempts", decal_id, TEXTURE_FETCH_RETRIES)
    return None


# -- Frame helpers ---------------------------------------------

def _frame_sort_key(name):
    m = re.search(r"\d+", name)
    return int(m.group()) if m else 0

def get_frames(frames_dir):
    if not os.path.isdir(frames_dir):
        log.error("Frames directory not found: %s", frames_dir)
        return []
    frames = [f for f in os.listdir(frames_dir)
              if f.lower().endswith((".png", ".jpg", ".jpeg"))]
    frames.sort(key=_frame_sort_key)
    return frames


# -- Upload worker ---------------------------------------------

def _upload_worker(frame, frames_dir, run_id, mapping):
    if abort_event.is_set():
        return frame, None, RESULT_ABORTED

    filepath = os.path.join(frames_dir, frame)
    operation, result_type = upload_frame(filepath, frame, run_id)

    if abort_event.is_set() and operation is None:
        return frame, None, RESULT_ABORTED

    if operation:
        with lock:
            mapping[frame] = {"operation": operation, "decal": None, "texture": None}
            save_mapping(run_id, mapping)

    time.sleep(random.uniform(MIN_DELAY, MAX_DELAY))

    return frame, operation, result_type


# -- Commands --------------------------------------------------

def _countdown(seconds, label=""):
    for remaining in range(seconds, 0, -1):
        print(f"\r[.] {label}{remaining}s ...", end="", flush=True)
        time.sleep(1)
    print("\r" + " " * 40 + "\r", end="")


def _print_ghost_warning():
    if not ghost_risk_frames:
        return

    print(f"\n{'='*60}")
    print(f"[!]  GHOST DECAL WARNING -- {len(ghost_risk_frames)} frame(s)")
    print(f"{'='*60}")
    print(f"These frames failed AFTER the upload request was sent.")
    print(f"Roblox may still create decals from them server-side.\n")
    for f in ghost_risk_frames[:20]:
        print(f"   * {f}")
    if len(ghost_risk_frames) > 20:
        print(f"   ... and {len(ghost_risk_frames) - 20} more")
    print(f"\n[!] Wait at least 5 minutes before appealing or re-uploading.")
    print(f"   Ghost decals appearing after moderation = extra strikes.")
    print(f"{'='*60}\n")

    notify(
        f"[!] GHOST WARNING -- {len(ghost_risk_frames)} frame(s) may still "
        f"appear as decals: {', '.join(ghost_risk_frames[:10])}"
        f"{'...' if len(ghost_risk_frames) > 10 else ''}"
    )


def cmd_upload(run_id, frames_dir, workers=DEFAULT_WORKERS):
    """Upload frames, watching for new files."""
    if not os.path.isdir(frames_dir):
        print(f"Frames directory not found: {frames_dir}")
        return

    mapping = load_mapping(run_id)
    reset_moderation_state()

    previously_moderated = {
        frame for frame, info in mapping.items()
        if info.get("moderated")
    }

    print(f"Watching '{frames_dir}' for frames  (run: {run_id})")
    print(f"Will stop after {WATCH_TIMEOUT}s with no new frames")
    print(f"Workers: {workers}")
    if previously_moderated:
        print(f"Skipping {len(previously_moderated)} previously moderated frames")
    notify(f"[>] Starting upload -- watching '{frames_dir}' (run: {run_id})")

    total_ok = 0
    total_fail = 0
    total_aborted = 0
    last_new_time = time.time()
    first_iteration = True

    while not abort_event.is_set():
        all_frames = get_frames(frames_dir)
        todo = [
            f for f in all_frames
            if f not in mapping
            and f not in moderated_frames
            and f not in previously_moderated
        ]

        if not todo:
            # If frames already exist but nothing to do on first check,
            # skip the wait entirely — there's nothing to wait for.
            if first_iteration and all_frames:
                print(f"[.] All {len(all_frames)} frames already processed — skipping wait.")
                break
            elapsed = time.time() - last_new_time
            remaining = WATCH_TIMEOUT - elapsed
            if remaining <= 0:
                break
            wait_step = min(5, remaining)
            print(f"\r[.] No new frames -- stopping in {remaining:.0f}s ... "
                  f"(total: {len(all_frames)} frames)", end="", flush=True)
            time.sleep(wait_step)
            continue
        first_iteration = False

        last_new_time = time.time()
        print(f"\n[>] Found {len(todo)} new frames (total: {len(all_frames)})")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_upload_worker, f, frames_dir, run_id, mapping): f
                for f in todo
            }

            with tqdm(total=len(futures), desc="Uploading", file=sys.stdout) as pbar:
                for future in as_completed(futures):
                    try:
                        frame, op, result_type = future.result()
                    except Exception as exc:
                        log.error("Worker crashed: %s", exc)
                        total_fail += 1
                        pbar.update(1)
                        continue

                    if result_type == RESULT_OK:
                        total_ok += 1
                    elif result_type == RESULT_ABORTED:
                        total_aborted += 1
                    elif result_type == RESULT_MODERATED:
                        with lock:
                            mapping[frame] = {
                                "operation": None, "decal": None,
                                "texture": None, "moderated": True,
                            }
                            save_mapping(run_id, mapping)
                    else:
                        total_fail += 1

                    pbar.update(1)

        if abort_event.is_set():
            break

        time.sleep(2)

    print()

    if abort_event.is_set():
        print(f"[!] UPLOAD ABORTED -- {moderation_count} frames moderated "
              f"(limit: {moderation_limit})")
        print(f"   Flagged frames: {', '.join(moderated_frames)}")
        print(f"   Before abort: {total_ok} uploaded, {total_fail} failed, "
              f"{total_aborted} skipped")
        print(f"\n   Remove the flagged frames from '{frames_dir}' and re-run.")
    else:
        print(f"Upload done -- {total_ok} succeeded, {total_fail} failed")
        if moderated_frames:
            print(f"   [!] Moderated (skipped): {', '.join(moderated_frames)}")

    _print_ghost_warning()

    notify(
        f"[OK] Upload done: {total_ok} ok, {total_fail} failed, "
        f"{len(moderated_frames)} moderated, "
        f"{len(ghost_risk_frames)} ghost-risk (run: {run_id})"
    )


def cmd_scrape(run_id, frames_dir=None, workers=DEFAULT_WORKERS,
               tex_workers=DEFAULT_TEX_WORKERS, cdn_warmup=DEFAULT_CDN_WARMUP):
    """Resolve pending operations -> decal IDs -> texture IDs.

    Parallelised with ThreadPoolExecutor for both stages.
    """
    mapping = load_mapping(run_id)
    if not mapping:
        print(f"No mapping found for run '{run_id}'. Run upload first.")
        return

    # -- Check for frames that were never uploaded --
    if frames_dir is None:
        frames_dir = os.path.join(_BASE_DIR, "frames", run_id)
    if os.path.isdir(frames_dir):
        all_pngs = sorted(
            f for f in os.listdir(frames_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg"))
        )
        missing = [f for f in all_pngs if f not in mapping]
        if missing:
            print(f"\n[!] {len(missing)} frame(s) in '{frames_dir}' were NEVER UPLOADED:")
            for f in missing[:15]:
                print(f"   * {f}")
            if len(missing) > 15:
                print(f"   ... and {len(missing) - 15} more")
            print(f"   These frames have no decal on Roblox -- re-upload needed.\n")

    # -- Summary --
    total = len(mapping)
    have_op    = sum(1 for v in mapping.values() if v.get("operation"))
    have_decal = sum(1 for v in mapping.values() if v.get("decal"))
    have_tex   = sum(1 for v in mapping.values() if v.get("texture"))
    moderated  = sum(1 for v in mapping.values() if v.get("moderated"))
    print(f"Mapping: {total} entries -- {have_op} operations, {have_decal} decals, "
          f"{have_tex} textures, {moderated} moderated")

    # -- 1) Operations -> decal IDs (PARALLEL) --
    pending_ops = {
        frame: info["operation"]
        for frame, info in mapping.items()
        if info.get("operation") and not info.get("decal")
        and not info.get("moderated")
    }

    op_failures = 0
    if pending_ops:
        print(f"Resolving {len(pending_ops)} operations -> decal IDs "
              f"({workers} workers) ...")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(poll_operation, op): frame
                for frame, op in pending_ops.items()
            }

            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="Resolving", file=sys.stdout):
                frame = futures[future]
                try:
                    decal_id = future.result()
                except Exception as exc:
                    log.error("Poll failed for %s: %s", frame, exc)
                    decal_id = None

                if decal_id:
                    with lock:
                        mapping[frame]["decal"] = decal_id
                        save_mapping(run_id, mapping)
                else:
                    op_failures += 1

        if op_failures:
            print(f"\n[!] {op_failures} operation(s) failed to resolve.")
            print(f"   If the upload account was terminated, the API key may be revoked.")
            print(f"   Frames with existing decal IDs can still be scraped for textures.\n")

    # -- CDN warmup --
    if pending_ops and op_failures < len(pending_ops):
        print(f"Waiting {cdn_warmup}s for Roblox CDN to process assets ...")
        _countdown(cdn_warmup, "CDN warmup: ")

    # -- 2) Decal IDs -> texture IDs (PARALLEL) --
    pending_tex = {
        frame: info["decal"]
        for frame, info in mapping.items()
        if info.get("decal") and not info.get("texture")
        and not info.get("moderated")
    }

    if pending_tex:
        # Validate the cookie BEFORE starting texture resolution so we
        # can distinguish "cookie is dead" from "individual assets removed".
        if not validate_cookie():
            print(
                "\n[!] Cookie is INVALID — skipping texture resolution.\n"
                "    Your cookie may have expired or the account was banned.\n"
                "    Update your cookie in the Profiles tab, then re-run scrape."
            )
        else:
            print(f"Fetching {len(pending_tex)} texture IDs "
                  f"({tex_workers} workers) ...")
            cookie_dead = False
            resolved_count = 0

            with ThreadPoolExecutor(max_workers=tex_workers) as pool:
                futures = {
                    pool.submit(fetch_texture_id, decal_id): frame
                    for frame, decal_id in pending_tex.items()
                }

                for future in tqdm(as_completed(futures), total=len(futures),
                                   desc="Textures", file=sys.stdout):
                    frame = futures[future]
                    try:
                        texture_id = future.result()
                    except CookieInvalidError:
                        texture_id = None
                        if not cookie_dead:
                            cookie_dead = True
                            log.error(
                                "Cookie rejected (HTTP 401) — cancelling "
                                "remaining texture lookups"
                            )
                            for f in futures:
                                f.cancel()
                    except Exception:
                        texture_id = None

                    if texture_id is not None:
                        resolved_count += 1

                    with lock:
                        mapping[frame]["texture"] = texture_id
                        save_mapping(run_id, mapping)

            if cookie_dead:
                print(
                    "\n[!] Cookie expired mid-resolution.\n"
                    "    Update your cookie in the Profiles tab,\n"
                    "    then re-run scrape to finish resolving."
                )
            elif resolved_count == 0 and len(pending_tex) > 0:
                print(
                    "\n[!] All decals returned 403 (unavailable).\n"
                    "    The uploading account was likely banned and Roblox\n"
                    "    removed its assets. You need to RE-UPLOAD the frames\n"
                    "    with your new account before resolving textures."
                )

    # -- 3) Write final output --
    all_frames = sorted(
        [f for f, info in mapping.items() if not info.get("moderated")],
        key=_frame_sort_key,
    )
    lines = []
    for frame in all_frames:
        tex = mapping[frame].get("texture")
        lines.append(str(tex) if tex else "PENDING")

    out = _output_path(run_id)
    _ensure_run_dir(run_id)
    with open(out, "w") as f:
        f.write("\n".join(lines))

    resolved = sum(1 for l in lines if l != "PENDING")
    pending_count = len(lines) - resolved
    print(f"\nScrape done -- {resolved}/{len(lines)} resolved -> {out}")
    if pending_count:
        print(f"   [!] {pending_count} still PENDING -- re-run scrape later to retry")
    notify(f"[i] Scrape done: {resolved}/{len(lines)} textures (run: {run_id})")


def cmd_fullrun(run_id, frames_dir, workers=DEFAULT_WORKERS,
                tex_workers=DEFAULT_TEX_WORKERS, cdn_warmup=DEFAULT_CDN_WARMUP):
    """Upload + gather in one shot.

    Step 1 (Upload): sends frames to Roblox (needs API key).
    Step 2 (Gather): searches inventory by name + resolves textures (cookie only).
    """
    cmd_upload(run_id, frames_dir, workers=workers)

    mapping = load_mapping(run_id)
    uploaded = sum(
        1 for v in mapping.values()
        if v.get("operation") and not v.get("moderated")
    )
    moderated = sum(1 for v in mapping.values() if v.get("moderated"))

    if uploaded == 0:
        if moderated:
            print("\n[!] All frames moderated — nothing to gather.")
        else:
            print("No new frames uploaded.")
        return

    # CDN warmup — give Roblox time to process the assets
    warmup = cdn_warmup + 30
    was_aborted = abort_event.is_set()
    if was_aborted:
        print(f"\n[!] Upload stopped — {len(moderated_frames)} frame(s) moderated.")
        print("    API key is likely disabled.")
        warmup = cdn_warmup + 60  # extra time for moderated accounts
        abort_event.clear()

        # Validate the cookie before wasting time on a doomed gather
        print("    Checking if your cookie is still valid ...")
        if not validate_cookie():
            print("\n[!] Cookie is INVALID — your account was likely banned.")
            print("    The gather step needs a working cookie to resolve textures.")
            print("    Switch to a different account's cookie in Profiles and re-run")
            print("    the 'search' step to finish resolving textures.")
            notify(
                "[!] Upload aborted (moderation) AND cookie is now invalid. "
                "Switch accounts and re-run search to finish."
            )
            return
        print("    Cookie is still valid — proceeding to gather.")

    print(f"\nWaiting {warmup}s for Roblox to process assets ...")
    _countdown(warmup, "Processing: ")

    # Gather: search inventory + resolve textures (cookie only, no API key)
    cmd_search(run_id, workers=workers, tex_workers=tex_workers)


def cmd_status(run_id):
    """Print a quick summary of a run's progress."""
    mapping = load_mapping(run_id)
    if not mapping:
        print(f"No data for run '{run_id}'.")
        return

    total     = len(mapping)
    moderated = sum(1 for v in mapping.values() if v.get("moderated"))
    uploaded  = sum(1 for v in mapping.values() if v.get("operation") and not v.get("moderated"))
    decals    = sum(1 for v in mapping.values() if v.get("decal"))
    textures  = sum(1 for v in mapping.values() if v.get("texture"))

    print(f"Run: {run_id}")
    print(f"  Frames:     {total}")
    print(f"  Uploaded:   {uploaded}")
    print(f"  Decals:     {decals}")
    print(f"  Textures:   {textures}")
    if moderated:
        print(f"  Moderated:  {moderated}")


def cmd_search(run_id, workers=DEFAULT_WORKERS, tex_workers=DEFAULT_TEX_WORKERS):
    """Search inventory for decals matching the run ID.

    Parallelised with a rate limiter to stay under 120 req/min.
    """
    print(f"Searching for decals with description '{run_id}' ...")

    if not ROBLOSECURITY:
        print("[X] ROBLOSECURITY cookie is required for search.")
        print("   Set it in the Profiles tab or your .env file.")
        return

    cookies = {".ROBLOSECURITY": ROBLOSECURITY}
    oc_headers = {"x-api-key": API_KEY}

    # -- Step 1: collect decal IDs from inventory ----------------
    all_decals = []
    name_matched = []
    legacy_candidates = []
    name_prefix = f"{run_id}_Frame_"
    cursor = ""
    page = 0

    print("Step 1/2: Listing decals from inventory ...")

    INVENTORY_MAX_RETRIES = 3
    INVENTORY_RETRY_DELAY = 30  # seconds between retries

    while True:
        page += 1
        params = {"limit": 100, "sortOrder": "Desc"}
        if cursor:
            params["cursor"] = cursor

        data = None
        for attempt in range(1, INVENTORY_MAX_RETRIES + 1):
            try:
                res = requests.get(
                    f"https://inventory.roblox.com/v2/users/{USER_ID}/inventory/13",
                    cookies=cookies,
                    params=params,
                    timeout=15,
                )
                if res.status_code in (400, 403, 429, 500, 503):
                    if attempt < INVENTORY_MAX_RETRIES:
                        print(f"  Inventory API returned {res.status_code} "
                              f"(attempt {attempt}/{INVENTORY_MAX_RETRIES}) "
                              f"-- retrying in {INVENTORY_RETRY_DELAY}s ...")
                        time.sleep(INVENTORY_RETRY_DELAY)
                        continue
                    else:
                        log.error("Inventory API returned %d after %d attempts: %s",
                                  res.status_code, attempt, res.text[:200])
                        break
                res.raise_for_status()
                data = res.json()
                break
            except Exception as exc:
                if attempt < INVENTORY_MAX_RETRIES:
                    print(f"  Inventory request error (attempt {attempt}/{INVENTORY_MAX_RETRIES}): {exc} "
                          f"-- retrying in {INVENTORY_RETRY_DELAY}s ...")
                    time.sleep(INVENTORY_RETRY_DELAY)
                else:
                    log.error("Inventory request failed (page %d): %s", page, exc)

        if data is None:
            break

        items = data.get("data", [])
        if not items:
            break

        for item in items:
            aid = item.get("assetId")
            if not aid:
                continue
            name = item.get("assetName", item.get("name", ""))
            entry = {"assetId": aid, "name": name}
            all_decals.append(entry)
            # Fast path: name starts with "{run_id}_Frame_" (new naming)
            if name.startswith(name_prefix):
                name_matched.append(entry)
            # Legacy fallback candidates: old "Frame_*" naming
            elif name.startswith("Frame_"):
                legacy_candidates.append(entry)

        print(f"  Page {page}: {len(items)} decals (matched: {len(name_matched)}, legacy: {len(legacy_candidates)})")

        cursor = data.get("nextPageCursor")
        if not cursor:
            break

    if not all_decals:
        print("[X] No decals found in inventory.")
        print("   Check that ROBLOX_USER_ID and ROBLOSECURITY are correct.")
        return

    # -- Step 2: determine matches (instant or legacy fallback) --
    found = []

    if name_matched:
        # Fast path — matched by name, no API calls needed
        found = name_matched
        print(f"Instant match: {len(found)} decals found by name (no API calls needed)")
    elif legacy_candidates:
        # Legacy fallback — old runs used "Frame_*" without run_id in name
        # Must check descriptions individually (slow)
        check_workers = max(workers, tex_workers)
        print(f"Legacy run detected: checking {len(legacy_candidates)} descriptions ({check_workers} workers) ...")
        limiter = _RateLimiter(calls_per_second=2.0)
        found_lock = threading.Lock()

        def _check_one(decal):
            aid = decal["assetId"]
            limiter.wait()
            try:
                detail = requests.get(
                    f"https://apis.roblox.com/assets/v1/assets/{aid}",
                    headers=oc_headers,
                    params={"readMask": "description,displayName"},
                    timeout=10,
                )
                if detail.status_code == 200:
                    info = detail.json()
                    if info.get("description") == run_id:
                        return {"assetId": aid, "name": info.get("displayName", decal["name"])}
                elif detail.status_code == 429:
                    log.warning("Rate limited, waiting 10s ...")
                    time.sleep(10)
                    limiter.wait()
                    detail = requests.get(
                        f"https://apis.roblox.com/assets/v1/assets/{aid}",
                        headers=oc_headers,
                        params={"readMask": "description,displayName"},
                        timeout=10,
                    )
                    if detail.status_code == 200:
                        info = detail.json()
                        if info.get("description") == run_id:
                            return {"assetId": aid, "name": info.get("displayName", decal["name"])}
            except Exception as exc:
                log.debug("Failed to fetch details for %s: %s", aid, exc)
            return None

        with ThreadPoolExecutor(max_workers=check_workers) as pool:
            futures = {pool.submit(_check_one, d): d for d in legacy_candidates}
            for future in tqdm(as_completed(futures), total=len(futures),
                               desc="Checking", file=sys.stdout):
                try:
                    result = future.result()
                except Exception:
                    result = None
                if result:
                    with found_lock:
                        found.append(result)

    if not found:
        print(f"[X] No decals for run '{run_id}' found in {len(all_decals)} inventory items.")
        return

    print(f"\nFound {len(found)} decals matching run '{run_id}'")

    # -- Step 2/2: parallel texture resolution -------------------
    print(f"Step 2/2: Resolving texture IDs ({tex_workers} workers) ...")
    mapping = load_mapping(run_id)

    # Build initial mapping entries for found decals
    for asset in found:
        name = asset.get("name", "")
        decal_id = asset["assetId"]
        # Extract frame number: handle both "{run_id}_Frame_0001" and "Frame_0001"
        m = re.search(r"Frame_(\d+)", name)
        frame_num = m.group(1) if m else re.sub(r"\D", "", name)
        if not frame_num:
            continue
        candidates = [f for f in mapping if re.sub(r"\D", "", f) == frame_num]
        key = candidates[0] if candidates else f"frame_{frame_num}.png"
        if key not in mapping:
            mapping[key] = {"operation": None, "decal": decal_id, "texture": None}
        else:
            mapping[key]["decal"] = decal_id

    # Parallel texture fetch
    pending = {
        f: info["decal"]
        for f, info in mapping.items()
        if info.get("decal") and not info.get("texture")
    }

    if pending:
        # Validate cookie upfront so we can distinguish "dead cookie"
        # from "assets removed by Roblox after the uploading account was banned".
        if not validate_cookie():
            print(
                "\n[!] Cookie is INVALID — skipping texture resolution.\n"
                "    Your cookie may have expired or the account was banned.\n"
                "    Update your cookie in the Profiles tab, then re-run search."
            )
            notify(
                "[!] Cookie invalid — texture resolution skipped. "
                "Update your cookie and re-run search."
            )
        else:
            cookie_dead = False
            resolved_count = 0

            with ThreadPoolExecutor(max_workers=tex_workers) as pool:
                futures = {
                    pool.submit(fetch_texture_id, did): frame
                    for frame, did in pending.items()
                }

                for future in tqdm(as_completed(futures), total=len(futures),
                                   desc="Resolving", file=sys.stdout):
                    frame = futures[future]
                    try:
                        texture_id = future.result()
                    except CookieInvalidError:
                        texture_id = None
                        if not cookie_dead:
                            cookie_dead = True
                            log.error(
                                "Cookie rejected (HTTP 401) — cancelling "
                                "remaining texture lookups"
                            )
                            for f in futures:
                                f.cancel()
                    except Exception:
                        texture_id = None

                    if texture_id is not None:
                        resolved_count += 1

                    with lock:
                        mapping[frame]["texture"] = texture_id

            if cookie_dead:
                print(
                    "\n[!] Cookie expired mid-resolution.\n"
                    "    Update your cookie in the Profiles tab,\n"
                    "    then re-run search to finish resolving."
                )
                notify(
                    "[!] Cookie expired during texture resolution. "
                    "Update your cookie and re-run search."
                )
            elif resolved_count == 0 and len(pending) > 0:
                print(
                    "\n[!] All decals returned 403 (unavailable).\n"
                    "    The uploading account was likely banned and Roblox\n"
                    "    removed its assets. You need to RE-UPLOAD the frames\n"
                    "    with your new account, then re-run search."
                )
                notify(
                    "[!] All decals unavailable (403). Assets removed after ban. "
                    "Re-upload with new account."
                )

    save_mapping(run_id, mapping)

    # Write assets.txt
    frames = sorted(mapping.keys(), key=_frame_sort_key)
    textures = [str(mapping[f].get("texture") or "PENDING") for f in frames]

    out = _output_path(run_id)
    _ensure_run_dir(run_id)
    with open(out, "w") as f:
        f.write("\n".join(textures))

    resolved = sum(1 for t in textures if t != "PENDING")
    print(f"Rebuilt {len(found)} entries -> {_mapping_path(run_id)}")
    print(f"Resolved {resolved}/{len(textures)} textures -> {out}")


# -- CLI -------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Roblox Frame Uploader",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subs = parser.add_subparsers(dest="command", required=True)

    def add_common(p):
        p.add_argument("--debug", action="store_true",
                        help="Enable debug logging")

    def add_run_id(p):
        p.add_argument("--run-id", required=True,
                        help="Run identifier (also used as the decal description)")

    def add_frames_dir(p):
        p.add_argument("--frames-dir", default=None,
                        help="Path to the folder of PNG frames (default: frames/<run_id>)")

    def add_all_worker_args(p):
        """Add all worker/config args to a subparser so the GUI can always pass them."""
        p.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"Upload/poll worker threads (default: {DEFAULT_WORKERS})")
        p.add_argument("--tex-workers", type=int, default=DEFAULT_TEX_WORKERS,
                        help=f"Texture fetch worker threads (default: {DEFAULT_TEX_WORKERS})")
        p.add_argument("--cdn-warmup", type=int, default=DEFAULT_CDN_WARMUP,
                        help=f"CDN warmup wait in seconds (default: {DEFAULT_CDN_WARMUP})")
        p.add_argument("--mod-limit", type=int, default=DEFAULT_MOD_LIMIT,
                        help=f"Moderation limit before abort (default: {DEFAULT_MOD_LIMIT})")

    # upload
    p = subs.add_parser("upload", help="Upload frames to Roblox")
    add_common(p); add_run_id(p); add_frames_dir(p)
    add_all_worker_args(p)

    # scrape
    p = subs.add_parser("scrape", help="Resolve decal & texture IDs")
    add_common(p); add_run_id(p); add_frames_dir(p)
    add_all_worker_args(p)

    # fullrun
    p = subs.add_parser("fullrun", help="Upload + scrape in one go")
    add_common(p); add_run_id(p); add_frames_dir(p)
    add_all_worker_args(p)

    # status
    p = subs.add_parser("status", help="Show progress for a run")
    add_common(p); add_run_id(p)
    add_all_worker_args(p)

    # search
    p = subs.add_parser("search", help="Find decals on Roblox by run ID")
    add_common(p); add_run_id(p)
    add_all_worker_args(p)

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s  %(message)s",
    )

    # -- Re-read credentials from environment -----------------
    # Profile env vars are injected by the GUI into this subprocess's
    # environment BEFORE it starts.  load_dotenv() (called at import
    # time) may also have loaded values.  Re-read here to make sure
    # the module-level globals reflect the final state.
    global API_KEY, USER_ID, WEBHOOK_URL, ROBLOSECURITY
    API_KEY        = os.getenv("ROBLOX_API_KEY") or None
    USER_ID        = _safe_int(os.getenv("ROBLOX_USER_ID"), 0)
    WEBHOOK_URL    = os.getenv("DISCORD_WEBHOOK_URL") or None
    ROBLOSECURITY  = _clean_cookie(os.getenv("ROBLOSECURITY"))

    # Default frames dir to <base>/frames/<run_id> if not specified
    if hasattr(args, "frames_dir") and args.frames_dir is None:
        args.frames_dir = os.path.join(_BASE_DIR, "frames", args.run_id)

    # Apply moderation limit if provided
    if hasattr(args, "mod_limit"):
        global moderation_limit
        moderation_limit = args.mod_limit

    # Worker counts
    w = getattr(args, "workers", DEFAULT_WORKERS)
    tw = getattr(args, "tex_workers", DEFAULT_TEX_WORKERS)
    cdw = getattr(args, "cdn_warmup", DEFAULT_CDN_WARMUP)

    # -- Validate credentials for the chosen command ---------
    cmd = args.command
    cred_errors = []
    if cmd in ("upload", "scrape", "fullrun", "search"):
        if not API_KEY:
            cred_errors.append("ROBLOX_API_KEY is not set")
    if cmd in ("upload", "fullrun", "search"):
        if not USER_ID:
            cred_errors.append("ROBLOX_USER_ID is not set (or zero)")
    if cmd in ("scrape", "fullrun", "search"):
        if not ROBLOSECURITY:
            cred_errors.append("ROBLOSECURITY cookie is not set")

    if cred_errors:
        print(f"\n[X] Missing credentials for '{cmd}':")
        for e in cred_errors:
            print(f"   * {e}")
        print(f"\nSet these in the Profiles tab or your .env file.")
        sys.exit(1)

    # -- Dispatch --------------------------------------------
    try:
        if cmd == "upload":
            cmd_upload(args.run_id, args.frames_dir, workers=w)
        elif cmd == "scrape":
            cmd_scrape(args.run_id, frames_dir=args.frames_dir,
                       workers=w, tex_workers=tw, cdn_warmup=cdw)
        elif cmd == "fullrun":
            cmd_fullrun(args.run_id, args.frames_dir,
                        workers=w, tex_workers=tw, cdn_warmup=cdw)
        elif cmd == "status":
            cmd_status(args.run_id)
        elif cmd == "search":
            cmd_search(args.run_id, workers=w, tex_workers=tw)
    except KeyboardInterrupt:
        print("\n[!] Interrupted.")
        sys.exit(130)
    except Exception as exc:
        print(f"\n[X] Unexpected error: {exc}")
        log.exception("Command '%s' failed", cmd)
        sys.exit(1)


if __name__ == "__main__":
    main()
