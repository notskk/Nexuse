import os
import customtkinter as ctk
from datetime import datetime
from src.gui.styles import UIStyle
from src.gui.components import CardFrame


def load_statistics_tab(parent, base_path):
    """Load and render the statistics tab."""
    for widget in parent.winfo_children():
        widget.destroy()

    scroll_frame = ctk.CTkScrollableFrame(
        parent, corner_radius=0, fg_color="transparent"
    )
    scroll_frame.pack(fill="both", expand=True)

    ctk.CTkLabel(
        scroll_frame, text="Statistics",
        font=UIStyle.HEADER_FONT,
    ).pack(pady=(20, 10), anchor="w", padx=20)

    # ── Gather data from frames/ ─────────────────────────────
    frames_root = os.path.join(base_path, "frames")
    run_data = []          # list of (name, frame_count, modified_ts)
    total_frames = 0

    if os.path.isdir(frames_root):
        for name in sorted(os.listdir(frames_root)):
            run_dir = os.path.join(frames_root, name)
            if os.path.isdir(run_dir):
                pngs = [f for f in os.listdir(run_dir)
                        if f.lower().endswith(".png")]
                mtime = os.path.getmtime(run_dir)
                run_data.append((name, len(pngs), mtime))
                total_frames += len(pngs)

    # ══════════════════════════════════════════════════════════
    #  Extraction Overview Card
    # ══════════════════════════════════════════════════════════
    overview_card = CardFrame(scroll_frame)
    overview_card.pack(fill="x", padx=10, pady=10)

    ctk.CTkLabel(
        overview_card, text="Extraction Overview",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=10, padx=15, anchor="w")

    overview_grid = ctk.CTkFrame(overview_card, fg_color="transparent")
    overview_grid.pack(pady=(0, 15), padx=20, fill="x")

    ctk.CTkLabel(
        overview_grid,
        text=f"Total Runs: {len(run_data)}",
        font=UIStyle.BODY_FONT,
    ).pack(side="left", expand=True)

    ctk.CTkLabel(
        overview_grid,
        text=f"Total Frames: {total_frames}",
        font=UIStyle.BODY_FONT, text_color="#4caf50",
    ).pack(side="left", expand=True)

    avg_frames = (total_frames // len(run_data)) if run_data else 0
    ctk.CTkLabel(
        overview_grid,
        text=f"Avg Frames/Run: {avg_frames}",
        font=UIStyle.BODY_FONT,
    ).pack(side="left", expand=True)

    # ══════════════════════════════════════════════════════════
    #  Per-Run Breakdown Card
    # ══════════════════════════════════════════════════════════
    runs_card = CardFrame(scroll_frame)
    runs_card.pack(fill="x", padx=10, pady=10)

    ctk.CTkLabel(
        runs_card, text="Extraction Runs",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=10, padx=15, anchor="w")

    history_frame = ctk.CTkScrollableFrame(
        runs_card, height=300, fg_color="transparent"
    )
    history_frame.pack(fill="x", padx=10, pady=(0, 15))

    if run_data:
        # Column headers
        hdr = ctk.CTkFrame(history_frame, fg_color="transparent")
        hdr.pack(fill="x", padx=10, pady=(0, 5))
        ctk.CTkLabel(
            hdr, text="Run ID",
            font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        ).pack(side="left", padx=5)
        ctk.CTkLabel(
            hdr, text="Frames",
            font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        ).pack(side="right", padx=(0, 80))
        ctk.CTkLabel(
            hdr, text="Modified",
            font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        ).pack(side="right", padx=5)

        # Most recent first
        for name, count, mtime in reversed(run_data):
            row = ctk.CTkFrame(history_frame, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)

            ctk.CTkLabel(
                row, text=name,
                font=UIStyle.SMALL_FONT,
            ).pack(side="left", padx=5)

            color = "#4caf50" if count > 0 else UIStyle.TEXT_SECONDARY_COLOR
            ctk.CTkLabel(
                row, text=str(count),
                font=UIStyle.SMALL_FONT, text_color=color,
            ).pack(side="right", padx=(0, 95))

            try:
                ts_str = datetime.fromtimestamp(mtime).strftime("%m/%d %H:%M")
            except Exception:
                ts_str = "–"
            ctk.CTkLabel(
                row, text=ts_str,
                font=UIStyle.SMALL_FONT,
                text_color=UIStyle.TEXT_SECONDARY_COLOR,
            ).pack(side="right", padx=5)
    else:
        ctk.CTkLabel(
            history_frame,
            text="No extraction runs yet.  Use Animation Uploader to get started.",
            font=UIStyle.BODY_FONT,
            text_color=UIStyle.TEXT_SECONDARY_COLOR,
        ).pack(pady=20)

    # ── Refresh ──────────────────────────────────────────────
    def _refresh():
        load_statistics_tab(parent, base_path)

    ctk.CTkButton(
        scroll_frame, text="Refresh Stats", command=_refresh,
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR,
        hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(pady=20)
