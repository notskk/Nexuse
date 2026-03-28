#!/usr/bin/env python3

import json
import os
import argparse
import sys
import base64

try:
    import zstandard as zstd
except ImportError:
    zstd = None

RUNS_DIR = "runs"

# ── Helpers ──────────────────────────────────────────────────

def load_texture_ids(run_id: str, runs_dir: str = None) -> list[str]:
    """Load texture IDs from a run's assets.txt file."""
    if runs_dir is None:
        runs_dir = RUNS_DIR
    assets_path = os.path.join(runs_dir, run_id, "assets.txt")

    if not os.path.exists(assets_path):
        raise FileNotFoundError(
            f"No assets file found for run '{run_id}' at {assets_path}"
        )

    with open(assets_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    if not lines:
        raise ValueError(f"{assets_path} is empty — nothing to build.")

    return lines


def build_sfx_entry(sfx_id: int, volume: int, start: float,
                    base_speed: float, replay_speed: float) -> dict:
    return {
        "VOLUME": volume,
        "K_NAME": "SFX",
        "ID": sfx_id,
        "START": start,
        "SPEED": round(base_speed * replay_speed, 6),
    }


def build_timeline(texture_ids: list[str], base_time: float,
                   visual_extra: float) -> list[dict]:
    """Build the visual + wait sequence for each frame."""
    entries = []

    visual_time = round(base_time + visual_extra, 6)
    wait_time = round(base_time, 6)

    for texture_id in texture_ids:
        visual = {
            "SIZE": 1,
            "OPACITY": 0,
            "TEXTURE": texture_id,
            "ALT COLOR": "255, 255, 255",
            "COLOR": "255, 255, 255",
            "AMOUNT": 1,
            "ALT ROTATION": "0, 0, 0",
            "POSITION": "0, 0, 0",
            "ALT POSITION": "0, 0, 0",
            "ALT SIZE": 1,
            "TIME": visual_time,
            "RUN ON SERVER": False,
            "BODY PART": "HumanoidRootPart",
            "K_NAME": "VISUAL",
            "LAST HIT": -1,
            "EFFECT": "Overlay",
            "ROTATION": "0, 0, 0",
            "ALT OPACITY": 0,
        }

        wait = {
            "TIME": wait_time,
            "K_NAME": "WAIT",
        }

        entries.append(visual)
        entries.append(wait)

    return entries


def build_skill_json(line: list[dict], skill_name: str) -> list[dict]:
    """Wrap the timeline into the full skill JSON structure."""
    return [
        {
            "ADD": False,
            "NAME": skill_name,
            "K_NAME": "SKILL",
            "KEY": 1,
            "DATA": {
                "Branch": {
                    "1": {
                        "Req": [],
                        "Line": line,
                    }
                },
                "Line": [
                    {
                        "BRANCH": "1",
                        "K_NAME": "BRANCH",
                    }
                ],
                "Prop": [],
                "Req": [],
            },
            "COOLDOWN": 0,
        }
    ]


def collapse_nested_data(obj):
    """Collapse DATA dict/list values into JSON strings (mirrors zstd_tool)."""
    if isinstance(obj, list):
        return [collapse_nested_data(i) for i in obj]
    elif isinstance(obj, dict):
        new_obj = {}
        for k, v in obj.items():
            if k.upper() == "DATA" and isinstance(v, (dict, list)):
                new_obj[k] = json.dumps(v, separators=(',', ':'))
            else:
                new_obj[k] = collapse_nested_data(v)
        return new_obj
    else:
        return obj


def encode_json(obj):
    """Encode a Python object to a Base64+zstd string."""
    collapsed = collapse_nested_data(obj)
    text = json.dumps(collapsed, separators=(',', ':'))
    cctx = zstd.ZstdCompressor()
    compressed = cctx.compress(text.encode('utf-8'))
    return base64.b64encode(compressed).decode('utf-8')


# ── Main ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Build a Roblox animation timeline from a workflow run",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--run-id", required=True,
                        help="Run ID to build timeline for")
    parser.add_argument("--fps", type=float, required=True,
                        help="Frames per second")
    parser.add_argument("--replay-speed", type=float, default=1.0,
                        help="Replay speed multiplier (default: 1.0)")
    parser.add_argument("--visual-extra", type=float, default=0.05,
                        help="Extra time added to visual TIME (default: 0.05)")
    parser.add_argument("--sfx-id", type=int, default=None,
                        help="SFX asset ID (omit to skip SFX entirely)")
    parser.add_argument("--sfx-volume", type=int, default=10,
                        help="SFX volume (default: 10)")
    parser.add_argument("--sfx-start", type=float, default=1.0,
                        help="SFX start time (default: 1.0)")
    parser.add_argument("--sfx-base-speed", type=float, default=1.0,
                        help="SFX base speed before replay multiplier (default: 1.0)")
    parser.add_argument("--output", default=None,
                        help="Custom output path (default: runs/<run_id>/timeline.json)")
    parser.add_argument("--skill-name", default="Unnamed",
                        help="Skill name in the output (default: Unnamed)")

    args = parser.parse_args()

    # ── Load textures from run ──
    try:
        raw_ids = load_texture_ids(args.run_id)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    pending = [i for i, tid in enumerate(raw_ids, 1) if tid == "PENDING"]
    texture_ids = [tid for tid in raw_ids if tid != "PENDING"]

    if pending:
        print(f"⚠ Skipping {len(pending)} PENDING frames: {pending[:10]}{'…' if len(pending) > 10 else ''}")
        print(f"  Try running scrape again to resolve them.")

    if not texture_ids:
        print("Error: No resolved texture IDs found. Nothing to build.")
        sys.exit(1)

    print(f"Building timeline: {len(texture_ids)} frames @ {args.fps} FPS × {args.replay_speed}x")

    # ── Calculate timing ──
    base_time = 1.0 / args.fps / args.replay_speed

    # ── Build JSON ──
    frames = build_timeline(texture_ids, base_time, args.visual_extra)

    if args.sfx_id is not None:
        sfx = build_sfx_entry(
            sfx_id=args.sfx_id,
            volume=args.sfx_volume,
            start=args.sfx_start,
            base_speed=args.sfx_base_speed,
            replay_speed=args.replay_speed,
        )
        timeline = [sfx] + frames
        print(f"SFX included — ID: {args.sfx_id}")
    else:
        timeline = frames
        print("No SFX (--sfx-id not provided)")

    skill_json = build_skill_json(timeline, args.skill_name)

    # ── Encode output ──
    if zstd is None:
        print("ERROR: zstandard not installed. Run: pip install zstandard", file=sys.stderr)
        sys.exit(1)

    encoded = encode_json(skill_json)

    if args.output:
        out_dir = os.path.dirname(args.output)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(encoded)
        print(f"Encoded string saved to {args.output}", file=sys.stderr)

    # Print the encoded string to stdout so the GUI can capture it
    print(encoded)

    # ── Summary (to stderr so it doesn't mix with the encoded output) ──
    print(f"\n✅ Encoded string ready!", file=sys.stderr)
    print(f"   Frames:       {len(texture_ids)}", file=sys.stderr)
    print(f"   FPS:          {args.fps}", file=sys.stderr)
    print(f"   Replay speed: {args.replay_speed}x", file=sys.stderr)
    print(f"   Wait TIME:    {base_time:.6f}", file=sys.stderr)
    print(f"   Visual TIME:  {base_time + args.visual_extra:.6f}", file=sys.stderr)
    if args.sfx_id is not None:
        print(f"   SFX SPEED:    {sfx['SPEED']}", file=sys.stderr)


if __name__ == "__main__":
    main()
