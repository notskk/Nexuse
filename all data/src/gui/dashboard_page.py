import os
import customtkinter as ctk
from src.gui.styles import UIStyle
from src.gui.components import CardFrame
from src.gui.utils import load_json_data


def load_dashboard_tab(parent, sidebar, callbacks, ui_context, base_path=None):
    """Load and render the Dashboard tab."""
    for widget in parent.winfo_children():
        widget.destroy()

    scroll_frame = ctk.CTkScrollableFrame(
        parent, corner_radius=0, fg_color="transparent"
    )
    scroll_frame.pack(fill="both", expand=True)

    # ══════════════════════════════════════════════════════════
    #  System Status Card
    # ══════════════════════════════════════════════════════════
    status_card = CardFrame(scroll_frame)
    status_card.pack(fill="x", padx=20, pady=(20, 10))

    status_header = ctk.CTkFrame(status_card, fg_color="transparent")
    status_header.pack(fill="x", padx=20, pady=(15, 0))
    ctk.CTkLabel(
        status_header, text="System Status",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(side="left")

    status_indicator = ctk.CTkLabel(
        status_header, text="●",
        font=("Segoe UI", 16), text_color="#4caf50",
    )
    status_indicator.pack(side="right")
    ui_context["status_indicator"] = status_indicator

    status_label = ctk.CTkLabel(
        status_card, text="Idle – Ready to start",
        font=UIStyle.BODY_FONT,
        text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    status_label.pack(pady=(5, 20), padx=20, anchor="w")
    ui_context["status_label"] = status_label

    # ══════════════════════════════════════════════════════════
    #  Statistics Summary Cards
    # ══════════════════════════════════════════════════════════
    if base_path:
        frames_root = os.path.join(base_path, "frames")

        # Scan the frames directory for run folders
        run_folders = []
        total_frames = 0
        if os.path.isdir(frames_root):
            for name in sorted(os.listdir(frames_root)):
                run_dir = os.path.join(frames_root, name)
                if os.path.isdir(run_dir):
                    pngs = [f for f in os.listdir(run_dir)
                            if f.lower().endswith(".png")]
                    run_folders.append((name, len(pngs)))
                    total_frames += len(pngs)

        stats_container = ctk.CTkFrame(
            scroll_frame, fg_color="transparent"
        )
        stats_container.pack(fill="x", padx=10, pady=10)

        def create_stat_card(parent_widget, title, value, subtext=None):
            card = CardFrame(parent_widget)
            card.pack(side="left", fill="both", expand=True, padx=10)

            container = ctk.CTkFrame(card, fg_color="transparent")
            container.pack(expand=True, fill="y", pady=15)

            ctk.CTkLabel(
                container, text=title,
                font=UIStyle.SMALL_FONT,
                text_color=UIStyle.TEXT_SECONDARY_COLOR,
            ).pack(anchor="center")
            ctk.CTkLabel(
                container, text=str(value),
                font=("Segoe UI", 28, "bold"),
            ).pack(anchor="center", pady=5)
            if subtext:
                ctk.CTkLabel(
                    container, text=subtext,
                    font=UIStyle.SMALL_FONT, text_color="gray",
                ).pack(anchor="center")
            else:
                ctk.CTkLabel(
                    container, text=" ",
                    font=UIStyle.SMALL_FONT,
                ).pack(anchor="center")
            return card

        create_stat_card(stats_container, "Extraction Runs", len(run_folders))
        create_stat_card(
            stats_container, "Total Frames", total_frames, "PNG files extracted"
        )

        # ══════════════════════════════════════════════════════
        #  Current Runs Card
        # ══════════════════════════════════════════════════════
        if run_folders:
            runs_card = CardFrame(scroll_frame)
            runs_card.pack(fill="x", padx=20, pady=10)

            ctk.CTkLabel(
                runs_card, text="Recent Runs",
                font=UIStyle.SUBHEADER_FONT,
            ).pack(pady=(15, 10), padx=15, anchor="w")

            for name, count in run_folders[-5:]:
                row = ctk.CTkFrame(runs_card, fg_color="transparent")
                row.pack(fill="x", padx=20, pady=2)
                ctk.CTkLabel(
                    row, text=name,
                    font=UIStyle.BODY_FONT,
                ).pack(side="left")
                ctk.CTkLabel(
                    row, text=f"{count} frames",
                    font=UIStyle.SMALL_FONT,
                    text_color=UIStyle.TEXT_SECONDARY_COLOR,
                ).pack(side="right")

            ctk.CTkLabel(
                runs_card, text=" ",
                font=UIStyle.SMALL_FONT,
            ).pack()  # spacing

    # ══════════════════════════════════════════════════════════
    #  Quick Actions Card
    # ══════════════════════════════════════════════════════════
    actions_card = CardFrame(scroll_frame)
    actions_card.pack(fill="x", padx=20, pady=10)

    ctk.CTkLabel(
        actions_card, text="Quick Actions",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=(15, 15), padx=20, anchor="w")

    actions_grid = ctk.CTkFrame(actions_card, fg_color="transparent")
    actions_grid.pack(fill="x", padx=15, pady=(0, 20))

    ctk.CTkButton(
        actions_grid, text="Animation Uploader",
        command=lambda: sidebar.show_page("Animation Uploader"),
        height=45, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR,
        hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="left", expand=True, fill="x", padx=5)

    ctk.CTkButton(
        actions_grid, text="Encoder / Decoder",
        command=lambda: sidebar.show_page("Encoder / Decoder"),
        height=45, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR,
        hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="left", expand=True, fill="x", padx=5)

    ctk.CTkButton(
        actions_grid, text="Statistics",
        command=lambda: sidebar.show_page("Statistics"),
        height=45, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR,
        hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="left", expand=True, fill="x", padx=5)
