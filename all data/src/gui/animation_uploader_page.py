import os
import re
import sys
import json
import subprocess
import threading
import logging
import tkinter as tk
import customtkinter as ctk
from tkinter import filedialog
from PIL import Image
from src.gui.styles import UIStyle
from src.gui.components import CardFrame, ModernEntry

logger = logging.getLogger(__name__)

# Profiles helper (imported lazily to avoid circular issues at module load)
def _get_profile_env(base_path):
    """Return env-var overrides from the active profile, or empty dict."""
    try:
        from src.gui.profiles_page import get_active_profile_env
        return get_active_profile_env(base_path)
    except Exception:
        return {}

# Lazy cv2 import
try:
    import cv2 as _cv2
except ImportError:
    _cv2 = None

# ── Regex for tqdm output parsing ────────────────────────────
_TQDM_PCT_RE = re.compile(r"(\d+)%\|")
_TQDM_FRAC_RE = re.compile(r"(\d+)/(\d+)")


def _fmt_time(seconds):
    """Format seconds as M:SS."""
    m, s = divmod(max(0, int(seconds)), 60)
    return f"{m}:{s:02d}"


def _make_progress_row(parent_card):
    """Create a Nexus-styled progress bar row inside a card.

    Returns (frame, progress_bar, pct_label, detail_label) where:
      - frame: the CTkFrame container (initially hidden)
      - progress_bar: CTkProgressBar (0.0–1.0)
      - pct_label: label showing "42 %"
      - detail_label: label showing "128 / 300 frames" etc.
    """
    frame = ctk.CTkFrame(parent_card, fg_color="transparent")

    bar = ctk.CTkProgressBar(
        frame,
        fg_color=UIStyle.INPUT_BG_COLOR,
        progress_color=UIStyle.ACCENT_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
        height=12,
    )
    bar.set(0)
    bar.pack(fill="x", padx=0, pady=(0, 4))

    info_row = ctk.CTkFrame(frame, fg_color="transparent")
    info_row.pack(fill="x")

    pct_label = ctk.CTkLabel(
        info_row, text="0 %",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.ACCENT_COLOR,
    )
    pct_label.pack(side="left")

    detail_label = ctk.CTkLabel(
        info_row, text="",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    detail_label.pack(side="right")

    return frame, bar, pct_label, detail_label


def load_animation_uploader_page(parent, base_path):
    """Load and render the Animation Uploader tab."""
    for widget in parent.winfo_children():
        widget.destroy()

    scroll_frame = ctk.CTkScrollableFrame(
        parent, corner_radius=0, fg_color="transparent"
    )
    scroll_frame.pack(fill="both", expand=True)

    ctk.CTkLabel(
        scroll_frame, text="Animation Uploader",
        font=UIStyle.HEADER_FONT,
    ).pack(pady=(20, 10), anchor="w", padx=20)

    # ── Shared state ─────────────────────────────────────────
    _proc_ref = [None]
    _action_btns = []
    _video_path_ref = [None]
    _video_info = {}

    frames_root = os.path.join(base_path, "frames")
    os.makedirs(frames_root, exist_ok=True)

    uploader_script = os.path.join(base_path, "src", "roblox_uploader.py")
    timeline_script = os.path.join(base_path, "src", "timeline_builder.py")

    # Player state
    _player = {
        "cap": None,
        "playing": False,
        "total_frames": 0,
        "current_frame": 0,
        "fps": 30.0,
        "after_id": None,
        "display_w": 480,
        "display_h": 270,
        "slider_updating": False,
    }

    MAX_DISPLAY_W = 560
    MAX_DISPLAY_H = 315

    # ══════════════════════════════════════════════════════════
    #  Video Source Card
    # ══════════════════════════════════════════════════════════
    video_card = CardFrame(scroll_frame)
    video_card.pack(fill="x", padx=10, pady=10)

    ctk.CTkLabel(
        video_card, text="Video Source",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=(15, 5), padx=15, anchor="w")

    # Browse row
    browse_row = ctk.CTkFrame(video_card, fg_color="transparent")
    browse_row.pack(fill="x", padx=15, pady=(0, 8))

    video_name_label = ctk.CTkLabel(
        browse_row, text="No video selected",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        anchor="w",
    )
    video_name_label.pack(side="left", fill="x", expand=True)

    # Video display area
    display_frame = ctk.CTkFrame(
        video_card, fg_color=UIStyle.INPUT_BG_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
        height=MAX_DISPLAY_H,
    )
    display_frame.pack(fill="x", padx=15, pady=(0, 4))
    display_frame.pack_propagate(False)

    video_label = ctk.CTkLabel(
        display_frame, text="No video loaded",
        font=UIStyle.BODY_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    video_label.place(relx=0.5, rely=0.5, anchor="center")

    # Player controls
    ctrl_frame = ctk.CTkFrame(video_card, fg_color="transparent")
    ctrl_frame.pack(fill="x", padx=15, pady=(4, 8))

    play_btn = ctk.CTkButton(
        ctrl_frame, text="▶  Play", width=90,
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    play_btn.pack(side="left", padx=(0, 4))

    stop_vid_btn = ctk.CTkButton(
        ctrl_frame, text="■  Stop", width=90,
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    stop_vid_btn.pack(side="left", padx=(0, 8))

    seek_slider = ctk.CTkSlider(
        ctrl_frame, from_=0, to=1000,
        fg_color=UIStyle.INPUT_BG_COLOR,
        progress_color=UIStyle.ACCENT_COLOR,
        button_color=UIStyle.ACCENT_COLOR,
        button_hover_color=UIStyle.BUTTON_HOVER_COLOR,
        height=14, number_of_steps=1000,
    )
    seek_slider.pack(side="left", fill="x", expand=True, padx=4)
    seek_slider.set(0)

    time_label = ctk.CTkLabel(
        ctrl_frame, text="0:00 / 0:00",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        width=90,
    )
    time_label.pack(side="left", padx=(8, 0))

    # Video info stat boxes
    stats_row = ctk.CTkFrame(video_card, fg_color="transparent")
    stats_row.pack(fill="x", padx=15, pady=(4, 10))

    _stat_labels = {}
    for stat_name in ["Duration", "Frame Rate", "Resolution", "Total Frames"]:
        box = ctk.CTkFrame(
            stats_row, fg_color=UIStyle.INPUT_BG_COLOR,
            corner_radius=UIStyle.CORNER_RADIUS,
        )
        box.pack(side="left", fill="x", expand=True, padx=3, pady=2)
        ctk.CTkLabel(
            box, text=stat_name, font=UIStyle.SMALL_FONT,
            text_color=UIStyle.TEXT_SECONDARY_COLOR,
        ).pack(pady=(8, 0))
        val = ctk.CTkLabel(
            box, text="—", font=UIStyle.BODY_FONT,
            text_color=UIStyle.TEXT_COLOR,
        )
        val.pack(pady=(0, 8))
        _stat_labels[stat_name] = val

    # Run ID + Debug row inside Video Source
    config_row = ctk.CTkFrame(video_card, fg_color="transparent")
    config_row.pack(fill="x", padx=15, pady=(4, 15))

    ctk.CTkLabel(
        config_row, text="Run ID:", font=UIStyle.BODY_FONT,
    ).pack(side="left", padx=(0, 5))

    run_id_entry = ModernEntry(config_row, width=200)
    run_id_entry.pack(side="left", padx=(0, 15))

    debug_var = ctk.BooleanVar(value=False)
    ctk.CTkCheckBox(
        config_row, text="Debug Logging",
        variable=debug_var, font=UIStyle.BODY_FONT,
    ).pack(side="left")

    # ── Player logic ─────────────────────────────────────────

    def _release_player():
        """Release video capture and cancel pending frame updates."""
        if _player["after_id"] is not None:
            try:
                parent.after_cancel(_player["after_id"])
            except Exception:
                pass
            _player["after_id"] = None
        _player["playing"] = False
        if _player["cap"] is not None:
            try:
                _player["cap"].release()
            except Exception:
                pass
            _player["cap"] = None
        play_btn.configure(text="▶  Play")

    def _display_frame(frame):
        """Convert a cv2 BGR frame → CTkImage and show it."""
        dw, dh = _player["display_w"], _player["display_h"]
        resized = _cv2.resize(frame, (dw, dh), interpolation=_cv2.INTER_LINEAR)
        rgb = _cv2.cvtColor(resized, _cv2.COLOR_BGR2RGB)
        img = Image.fromarray(rgb)
        ctk_img = ctk.CTkImage(
            light_image=img, dark_image=img, size=(dw, dh)
        )
        video_label.configure(image=ctk_img, text="")
        video_label._ctk_img = ctk_img  # prevent garbage collection

    def _update_time():
        """Sync time label and seek slider with current playback position."""
        fps = _player["fps"] if _player["fps"] > 0 else 30
        cur_s = _player["current_frame"] / fps
        tot_s = _player["total_frames"] / fps
        time_label.configure(text=f"{_fmt_time(cur_s)} / {_fmt_time(tot_s)}")
        if _player["total_frames"] > 0:
            _player["slider_updating"] = True
            seek_slider.set(
                _player["current_frame"] / _player["total_frames"] * 1000
            )
            _player["slider_updating"] = False

    def _load_video(path):
        """Open a video file, display first frame, populate stats."""
        if _cv2 is None:
            video_name_label.configure(
                text="OpenCV not installed — pip install opencv-python",
                text_color="#f44336",
            )
            return

        _release_player()

        cap = _cv2.VideoCapture(path)
        if not cap.isOpened():
            video_name_label.configure(
                text="Cannot open video", text_color="#f44336"
            )
            return

        # Read metadata
        fps = cap.get(_cv2.CAP_PROP_FPS) or 30
        total = int(cap.get(_cv2.CAP_PROP_FRAME_COUNT))
        w = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT))
        dur = total / fps if fps > 0 else 0

        _video_info.update({
            "fps": fps, "total_frames": total,
            "width": w, "height": h, "duration_s": dur,
        })

        # Calculate display size maintaining aspect ratio
        if w > 0 and h > 0:
            scale = min(MAX_DISPLAY_W / w, MAX_DISPLAY_H / h)
            _player["display_w"] = int(w * scale)
            _player["display_h"] = int(h * scale)
        else:
            _player["display_w"] = MAX_DISPLAY_W
            _player["display_h"] = MAX_DISPLAY_H

        _player["cap"] = cap
        _player["fps"] = fps
        _player["total_frames"] = total
        _player["current_frame"] = 0

        # Show first frame
        ret, frame = cap.read()
        if ret:
            _display_frame(frame)
        cap.set(_cv2.CAP_PROP_POS_FRAMES, 0)
        _player["current_frame"] = 0

        # Update labels
        video_name_label.configure(
            text=os.path.basename(path), text_color=UIStyle.TEXT_COLOR
        )
        mins, secs = divmod(int(dur), 60)
        _stat_labels["Duration"].configure(text=f"{mins}m {secs}s")
        _stat_labels["Frame Rate"].configure(text=f"{fps:.1f} fps")
        _stat_labels["Resolution"].configure(text=f"{w}×{h}")
        _stat_labels["Total Frames"].configure(text=f"{total:,}")

        _update_time()
        seek_slider.set(0)



    def _play_video():
        """Toggle play / pause."""
        if _player["cap"] is None:
            return
        if _player["playing"]:
            _pause_video()
            return
        _player["playing"] = True
        play_btn.configure(text="⏸  Pause")
        _frame_loop()

    def _pause_video():
        """Pause playback."""
        _player["playing"] = False
        play_btn.configure(text="▶  Play")
        if _player["after_id"]:
            try:
                parent.after_cancel(_player["after_id"])
            except Exception:
                pass
            _player["after_id"] = None

    def _stop_video():
        """Stop playback, reset to frame 0."""
        _pause_video()
        if _player["cap"] is not None:
            _player["cap"].set(_cv2.CAP_PROP_POS_FRAMES, 0)
            _player["current_frame"] = 0
            ret, frame = _player["cap"].read()
            if ret:
                _display_frame(frame)
            _player["cap"].set(_cv2.CAP_PROP_POS_FRAMES, 0)
            _player["current_frame"] = 0
        _update_time()
        seek_slider.set(0)

    def _frame_loop():
        """Read next frame and schedule the following one."""
        if not _player["playing"] or _player["cap"] is None:
            return

        ret, frame = _player["cap"].read()
        if not ret:
            # Reached end of video
            _pause_video()
            _player["current_frame"] = _player["total_frames"]
            _update_time()
            return

        _display_frame(frame)
        _player["current_frame"] = int(
            _player["cap"].get(_cv2.CAP_PROP_POS_FRAMES)
        )
        _update_time()

        delay = max(1, int(1000 / _player["fps"]))
        _player["after_id"] = parent.after(delay, _frame_loop)

    def _on_seek(value):
        """Handle user dragging the seek slider."""
        if _player["slider_updating"] or _player["cap"] is None:
            return

        was_playing = _player["playing"]
        if was_playing:
            _pause_video()

        frame_num = int(float(value) / 1000 * _player["total_frames"])
        _player["cap"].set(_cv2.CAP_PROP_POS_FRAMES, frame_num)

        ret, frame = _player["cap"].read()
        if ret:
            _display_frame(frame)

        _player["current_frame"] = frame_num
        _update_time()

        if was_playing:
            _player["playing"] = True
            play_btn.configure(text="⏸  Pause")
            _frame_loop()

    # Wire up player controls
    seek_slider.configure(command=_on_seek)
    play_btn.configure(command=_play_video)
    stop_vid_btn.configure(command=_stop_video)

    def _browse_video():
        path = filedialog.askopenfilename(
            filetypes=[
                ("Video Files", "*.mp4 *.avi *.mkv *.mov *.webm"),
                ("All Files", "*.*"),
            ]
        )
        if path:
            _video_path_ref[0] = path
            _load_video(path)

    browse_btn = ctk.CTkButton(
        browse_row, text="Browse", command=_browse_video,
        width=80, height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    browse_btn.pack(side="right")


    # ══════════════════════════════════════════════════════════
    #  Create Animation Card
    # ══════════════════════════════════════════════════════════
    pipeline_card = CardFrame(scroll_frame)
    pipeline_card.pack(fill="x", padx=10, pady=10)

    pipeline_hdr = ctk.CTkFrame(pipeline_card, fg_color="transparent")
    pipeline_hdr.pack(fill="x", padx=15, pady=(15, 5))

    ctk.CTkLabel(
        pipeline_hdr, text="Create Animation",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(side="left")

    upload_status = ctk.CTkLabel(
        pipeline_hdr, text="Ready",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    upload_status.pack(side="right")

    # ── Active-profile info banner ───────────────────────────
    profile_banner = ctk.CTkFrame(
        pipeline_card, fg_color=UIStyle.INPUT_BG_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    profile_banner.pack(fill="x", padx=15, pady=(6, 4))

    profile_icon = ctk.CTkLabel(
        profile_banner, text="👤",
        font=UIStyle.BODY_FONT,
    )
    profile_icon.pack(side="left", padx=(10, 4), pady=6)

    profile_name_lbl = ctk.CTkLabel(
        profile_banner, text="No active profile — go to Profiles tab to set one",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        anchor="w",
    )
    profile_name_lbl.pack(side="left", fill="x", expand=True, pady=6)

    def _refresh_profile_banner():
        try:
            from src.gui.profiles_page import load_profiles as _lp
            data = _lp(base_path)
            active = data.get("active_profile")
            if active:
                profile_name_lbl.configure(
                    text=f"Active profile: {active}",
                    text_color="#4caf50",
                )
            else:
                profile_name_lbl.configure(
                    text="No active profile — go to Profiles tab to set one",
                    text_color=UIStyle.TEXT_SECONDARY_COLOR,
                )
        except Exception:
            pass
        try:
            parent.after(3000, _refresh_profile_banner)
        except Exception:
            pass

    _refresh_profile_banner()

    # ── Step progress rows ────────────────────────────────────
    steps_frame = ctk.CTkFrame(pipeline_card, fg_color="transparent")
    steps_frame.pack(fill="x", padx=15, pady=(8, 2))
    steps_frame.pack_forget()  # hidden until pipeline starts

    def _make_step_row(parent_frame, label_text):
        """Create a labeled progress bar row for a pipeline step."""
        row = ctk.CTkFrame(parent_frame, fg_color="transparent")
        row.pack(fill="x", pady=3)

        lbl = ctk.CTkLabel(
            row, text=label_text, width=80, anchor="w",
            font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        )
        lbl.pack(side="left")

        bar = ctk.CTkProgressBar(
            row,
            fg_color=UIStyle.INPUT_BG_COLOR,
            progress_color=UIStyle.ACCENT_COLOR,
            corner_radius=UIStyle.CORNER_RADIUS,
            height=10,
        )
        bar.set(0)
        bar.pack(side="left", fill="x", expand=True, padx=(4, 8))

        pct = ctk.CTkLabel(
            row, text="", width=45,
            font=UIStyle.SMALL_FONT, text_color=UIStyle.ACCENT_COLOR,
        )
        pct.pack(side="left")

        detail = ctk.CTkLabel(
            row, text="Waiting…", width=140, anchor="e",
            font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        )
        detail.pack(side="right")

        return row, bar, pct, detail

    s1_row, s1_bar, s1_pct, s1_detail = _make_step_row(steps_frame, "Extract")
    s2_row, s2_bar, s2_pct, s2_detail = _make_step_row(steps_frame, "Upload")
    s3_row, s3_bar, s3_pct, s3_detail = _make_step_row(steps_frame, "Gather")
    s4_row, s4_bar, s4_pct, s4_detail = _make_step_row(steps_frame, "Encode")

    # ── Create Animation button ───────────────────────────────
    ca_btn = ctk.CTkButton(
        pipeline_card, text="🎬  Create Animation",
        command=lambda: _create_animation(),
        height=42, font=UIStyle.SUBHEADER_FONT,
        fg_color="#1a5a2e", hover_color="#267a3e",
        text_color="#4caf50",
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    ca_btn.pack(fill="x", padx=15, pady=(10, 4))
    _action_btns.append(ca_btn)

    # ── Stop button ───────────────────────────────────────────
    stop_btn = ctk.CTkButton(
        pipeline_card, text="Stop",
        command=lambda: _stop_process(),
        height=UIStyle.BUTTON_HEIGHT,
        font=UIStyle.BODY_FONT,
        fg_color="#c42b1c", hover_color="#8f1f14",
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    stop_btn.pack(fill="x", padx=15, pady=(4, 8))

    # ── Encoded output textbox ─────────────────────────────────
    tl_output_frame = ctk.CTkFrame(pipeline_card, fg_color="transparent")
    tl_output_frame.pack(fill="x", padx=15, pady=(8, 2))
    tl_output_frame.pack_forget()

    tl_output_hdr = ctk.CTkFrame(tl_output_frame, fg_color="transparent")
    tl_output_hdr.pack(fill="x", pady=(0, 4))

    ctk.CTkLabel(
        tl_output_hdr, text="Encoded Output",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    ).pack(side="left")

    def _copy_tl_output():
        text = tl_output_box.get("1.0", "end-1c")
        if text.strip():
            parent.clipboard_clear()
            parent.clipboard_append(text)
            upload_status.configure(text="Copied!", text_color="#4caf50")

    ctk.CTkButton(
        tl_output_hdr, text="Copy", command=_copy_tl_output,
        width=54, height=24, font=UIStyle.SMALL_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="right")

    tl_output_box = ctk.CTkTextbox(
        tl_output_frame, height=80,
        font=("Consolas", 11),
        fg_color=UIStyle.INPUT_BG_COLOR,
        text_color=UIStyle.TEXT_COLOR,
        border_color=UIStyle.BORDER_COLOR,
        border_width=1,
        corner_radius=UIStyle.CORNER_RADIUS,
        wrap="none",
    )
    tl_output_box.pack(fill="x")
    tl_output_box.configure(state="disabled")

    def _set_tl_output(text):
        tl_output_box.configure(state="normal")
        tl_output_box.delete("1.0", "end")
        tl_output_box.insert("1.0", text)
        tl_output_box.configure(state="disabled")
        tl_output_frame.pack(fill="x", padx=15, pady=(8, 12))

    # ── Padding at bottom ─────────────────────────────────────
    ctk.CTkFrame(pipeline_card, fg_color="transparent", height=8).pack()

    # ── Helper functions ──────────────────────────────────────

    def _set_buttons(state):
        for b in _action_btns:
            b.configure(state=state)

    def _read_uploader_config():
        try:
            cfg_path = os.path.join(base_path, "config", "gui_config.json")
            with open(cfg_path) as f:
                cfg = json.load(f)
            up = cfg.get("Uploader", {})
            return {
                "workers": up.get("max_workers", 2),
                "tex_workers": up.get("tex_workers", 8),
                "cdn_warmup": up.get("cdn_warmup", 60),
                "mod_limit": up.get("mod_limit", 1),
            }
        except Exception:
            return {"workers": 2, "tex_workers": 8, "cdn_warmup": 60, "mod_limit": 1}

    def _get_uploader_args(need_frames=True):
        rid = run_id_entry.get().strip()
        if not rid:
            upload_status.configure(
                text="⚠ Run ID required", text_color="#f44336"
            )
            return None
        fdir = os.path.join(frames_root, rid)
        args = ["--run-id", rid]
        if need_frames:
            args += ["--frames-dir", fdir]
        if debug_var.get():
            args.append("--debug")
        ucfg = _read_uploader_config()
        args += [
            "--workers", str(ucfg["workers"]),
            "--tex-workers", str(ucfg["tex_workers"]),
            "--cdn-warmup", str(ucfg["cdn_warmup"]),
            "--mod-limit", str(ucfg["mod_limit"]),
        ]
        return args

    def _stop_process():
        proc = _proc_ref[0]
        if proc and proc.poll() is None:
            proc.terminate()
            upload_status.configure(text="⏹ Stopped", text_color="#ff9800")
            _set_buttons("normal")

    def _reset_steps():
        """Show steps frame and reset all progress bars."""
        for bar, pct, det in [
            (s1_bar, s1_pct, s1_detail),
            (s2_bar, s2_pct, s2_detail),
            (s3_bar, s3_pct, s3_detail),
            (s4_bar, s4_pct, s4_detail),
        ]:
            bar.set(0)
            pct.configure(text="")
            det.configure(text="Waiting…")
        steps_frame.pack(fill="x", padx=15, pady=(8, 2),
                        after=profile_banner)

    def _mark_step_done(bar, pct, detail, text="Done"):
        bar.set(1.0)
        pct.configure(text="100 %")
        detail.configure(text=text)

    def _create_animation():
        """Full pipeline: extract → upload + scrape → build timeline → encode."""
        rid = run_id_entry.get().strip()
        video = _video_path_ref[0]
        fps_val = str(int(_video_info.get("fps", 30)))

        if not video or not os.path.exists(video):
            upload_status.configure(
                text="⚠ Select a video first", text_color="#f44336")
            return
        if not rid:
            upload_status.configure(
                text="⚠ Run ID required", text_color="#f44336")
            return

        if _proc_ref[0] and _proc_ref[0].poll() is None:
            upload_status.configure(
                text="⚠ Process already running", text_color="#ff9800")
            return

        ext_params = {"output_format": "png"}
        uploader_args = _get_uploader_args(need_frames=True)
        if not uploader_args:
            return

        _set_buttons("disabled")
        _reset_steps()
        if _player["playing"]:
            _pause_video()

        def _pipeline():
            try:
                # ── Step 1: Extract frames ─────────────────────
                parent.after(0, lambda: upload_status.configure(
                    text="Step 1/4 — Extracting frames…",
                    text_color="#ff9800"))
                parent.after(0, lambda: s1_detail.configure(text="Checking…"))

                from src.video_extractor import extract_frames
                out_dir = os.path.join(frames_root, rid)

                # Skip extraction if frames already exist for this run ID
                existing_pngs = []
                if os.path.isdir(out_dir):
                    existing_pngs = [f for f in os.listdir(out_dir)
                                     if f.lower().endswith(".png")]
                if existing_pngs:
                    frame_count = len(existing_pngs)
                    parent.after(0, lambda c=frame_count: (
                        s1_bar.set(1.0),
                        s1_pct.configure(text="100 %"),
                        s1_detail.configure(
                            text=f"{c:,} frames (cached)"),
                        upload_status.configure(
                            text="Step 1/4 — Frames already extracted ✓",
                            text_color="#4caf50"),
                    ))
                else:
                    def _ext_cb(current, total):
                        if total > 0:
                            pct = current / total
                            parent.after(0, lambda p=pct, c=current, t=total: (
                                s1_bar.set(p),
                                s1_pct.configure(text=f"{int(p * 100)} %"),
                                s1_detail.configure(text=f"{c:,} / {t:,}"),
                            ))

                    result = extract_frames(
                        video, out_dir,
                        progress_callback=_ext_cb, **ext_params)
                    frame_count = result["extracted_frames"]

                parent.after(0, lambda c=frame_count: (
                    _mark_step_done(s1_bar, s1_pct, s1_detail,
                                    f"{c:,} frames"),
                ))

                import time as _time
                _time.sleep(0.3)

                # ── Step 2+3: Upload + Gather (subprocess) ─────
                parent.after(0, lambda: upload_status.configure(
                    text="Step 2/4 — Uploading…",
                    text_color="#ff9800"))
                parent.after(0, lambda: s2_detail.configure(text="Starting…"))

                env = os.environ.copy()
                env["PYTHONUNBUFFERED"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                env.update(_get_profile_env(base_path))

                cmd = [sys.executable, uploader_script,
                       "fullrun"] + uploader_args
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    cwd=base_path, env=env)
                _proc_ref[0] = proc

                _ERR_TAGS = (
                    "❌", "ERROR", "✗", "CRITICAL",
                    "MODERATION LIMIT", "Traceback",
                    "Exception", "ModuleNotFoundError")

                # Phase detection from tqdm desc
                _phase = ["upload"]  # "upload", "cdn", "resolve"
                fd = proc.stdout.fileno()
                buf = ""
                last_err = ""

                def _route_progress(line):
                    """Route tqdm/status output to the correct step bar."""
                    nonlocal last_err

                    # Detect phase changes from output
                    lower = line.lower()

                    # CDN warmup / processing countdown
                    if "processing:" in lower or "cdn warmup" in lower or "waiting" in lower:
                        if _phase[0] == "upload":
                            # Upload done, entering CDN warmup
                            parent.after(0, lambda: (
                                _mark_step_done(s2_bar, s2_pct, s2_detail, "Done"),
                                upload_status.configure(
                                    text="Step 3/4 — CDN warmup…",
                                    text_color="#ff9800"),
                            ))
                            _phase[0] = "cdn"
                        # Show countdown in s3 detail
                        rm = re.search(r"(\d+)s", line)
                        if rm:
                            parent.after(0, lambda t=rm.group(1): (
                                s3_detail.configure(text=f"Warmup: {t}s"),
                            ))
                        return

                    # Search/gather phase detection
                    if "searching for decals" in lower or "listing decals" in lower:
                        if _phase[0] != "gather":
                            _phase[0] = "gather"
                            parent.after(0, lambda: (
                                upload_status.configure(
                                    text="Step 3/4 — Gathering…",
                                    text_color="#ff9800"),
                                s3_detail.configure(text="Searching inventory…"),
                            ))
                        return

                    # Inventory page progress
                    if "page " in lower and "matched:" in lower:
                        pm_page = re.search(r"page\s+(\d+)", lower)
                        pm_match = re.search(r"matched:\s*(\d+)", lower)
                        if pm_page and pm_match:
                            parent.after(0, lambda p=pm_page.group(1), m=pm_match.group(1): (
                                s3_detail.configure(text=f"Page {p} — {m} matched"),
                            ))
                        return

                    # Instant match result
                    if "instant match" in lower or ("found" in lower and "decals" in lower):
                        dm = re.search(r"(\d+)\s+decals", lower)
                        if dm:
                            parent.after(0, lambda c=dm.group(1): (
                                s3_detail.configure(text=f"{c} decals found"),
                            ))
                        return

                    pm = _TQDM_PCT_RE.search(line)
                    fm = _TQDM_FRAC_RE.search(line)

                    if pm:
                        p = int(pm.group(1))
                        prefix = line[:pm.start()].strip().lower()

                        if "resolv" in prefix or "texture" in prefix or "check" in prefix:
                            # Gather phase (resolving textures / checking descriptions)
                            if _phase[0] not in ("gather", "resolve"):
                                _phase[0] = "gather"
                                parent.after(0, lambda: (
                                    upload_status.configure(
                                        text="Step 3/4 — Resolving textures…",
                                        text_color="#ff9800"),
                                    s3_detail.configure(text="Resolving…"),
                                ))
                            bar, pct_w, det = s3_bar, s3_pct, s3_detail
                        else:
                            # Upload phase
                            bar, pct_w, det = s2_bar, s2_pct, s2_detail

                        parent.after(0, lambda b=bar, pw=pct_w, v=p: (
                            b.set(v / 100),
                            pw.configure(text=f"{v} %"),
                        ))
                        if fm:
                            c, t = int(fm.group(1)), int(fm.group(2))
                            parent.after(0, lambda d=det, c=c, t=t:
                                d.configure(text=f"{c:,} / {t:,}"))

                    if any(m in line for m in _ERR_TAGS):
                        last_err = line
                        logger.error(line)
                    elif not pm:
                        logger.info(line)

                while True:
                    try:
                        raw = os.read(fd, 4096)
                    except OSError:
                        break
                    if not raw:
                        stripped = buf.rstrip()
                        if stripped:
                            _route_progress(stripped)
                        break
                    chunk = raw.decode("utf-8", errors="replace")
                    for ch in chunk:
                        if ch in ("\r", "\n"):
                            line = buf.rstrip()
                            buf = ""
                            if line:
                                _route_progress(line)
                        else:
                            buf += ch

                proc.wait()
                if proc.returncode != 0:
                    err = last_err or f"Exit code {proc.returncode}"
                    if len(err) > 100:
                        err = err[:97] + "…"
                    parent.after(0, lambda t=err:
                        upload_status.configure(
                            text=f"✗ {t}", text_color="#f44336"))
                    return

                # Mark upload + resolve done
                parent.after(0, lambda: (
                    _mark_step_done(s2_bar, s2_pct, s2_detail, "Done"),
                    _mark_step_done(s3_bar, s3_pct, s3_detail, "Done"),
                ))

                # ── Step 4: Build timeline + encode ────────────
                parent.after(0, lambda: upload_status.configure(
                    text="Step 4/4 — Encoding…",
                    text_color="#ff9800"))
                parent.after(0, lambda: (
                    s4_bar.set(0.3),
                    s4_detail.configure(text="Building…"),
                ))

                from src.timeline_builder import (
                    load_texture_ids, build_timeline as _build_tl,
                    build_skill_json, encode_json,
                )
                runs_dir = os.path.join(base_path, "runs")
                raw_ids = load_texture_ids(rid, runs_dir=runs_dir)
                tex_ids = [t for t in raw_ids if t != "PENDING"]
                n_pending = len(raw_ids) - len(tex_ids)

                if not tex_ids:
                    parent.after(0, lambda: upload_status.configure(
                        text="✗ No resolved textures",
                        text_color="#f44336"))
                    return

                parent.after(0, lambda: (
                    s4_bar.set(0.6),
                    s4_detail.configure(text="Encoding…"),
                ))

                tl_fps = float(fps_val)

                base_time = 1.0 / tl_fps
                tl_frames = _build_tl(tex_ids, base_time, 0.05)
                skill = build_skill_json(tl_frames, "Unnamed")
                encoded = encode_json(skill)

                parent.after(0, lambda e=encoded: _set_tl_output(e))
                parent.after(0, lambda e=encoded: (
                    parent.clipboard_clear(),
                    parent.clipboard_append(e),
                ))

                parent.after(0, lambda: _mark_step_done(
                    s4_bar, s4_pct, s4_detail,
                    f"{len(tex_ids):,} frames"))

                msg = f"✓ {len(tex_ids)} frames → encoded & copied!"
                if n_pending:
                    msg += f" ({n_pending} pending)"
                parent.after(0, lambda t=msg:
                    upload_status.configure(
                        text=t, text_color="#4caf50"))

            except Exception as e:
                parent.after(0, lambda t=str(e):
                    upload_status.configure(
                        text=f"✗ {t}", text_color="#f44336"))
            finally:
                parent.after(0, lambda: _set_buttons("normal"))

        threading.Thread(target=_pipeline, daemon=True).start()
