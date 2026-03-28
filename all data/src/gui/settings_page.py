import os
import json
import customtkinter as ctk
from tkinter import messagebox
from src.gui.styles import UIStyle
from src.gui.components import CardFrame, ModernEntry
from src.gui.themes import load_available_themes


def _make_setting_row(parent, label_text, default, tooltip=None, row=0):
    """Create a label + entry row for a numeric setting.

    Returns the ModernEntry widget.
    """
    ctk.CTkLabel(
        parent, text=label_text, font=UIStyle.BODY_FONT,
    ).grid(row=row, column=0, padx=(0, 10), pady=5, sticky="w")

    entry = ModernEntry(parent, width=80)
    entry.insert(0, str(default))
    entry.grid(row=row, column=1, padx=0, pady=5, sticky="w")

    if tooltip:
        hint = ctk.CTkLabel(
            parent, text=tooltip, font=UIStyle.SMALL_FONT,
            text_color=UIStyle.TEXT_SECONDARY_COLOR,
        )
        hint.grid(row=row, column=2, padx=(10, 0), pady=5, sticky="w")

    return entry


def load_settings_tab(parent, config, shared_vars, save_callback, base_path,
                      root_ref, restart_callback=None,
                      update_shortcuts_callback=None):
    """Populate the settings tab."""
    for widget in parent.winfo_children():
        widget.destroy()

    scroll_frame = ctk.CTkScrollableFrame(
        parent, corner_radius=0, fg_color="transparent",
    )
    scroll_frame.pack(fill="both", expand=True)

    ctk.CTkLabel(
        scroll_frame, text="Settings", font=UIStyle.HEADER_FONT,
    ).pack(pady=(20, 10), anchor="w", padx=20)

    # ══════════════════════════════════════════════════════════
    #  Display Settings
    # ══════════════════════════════════════════════════════════
    display_card = CardFrame(scroll_frame)
    display_card.pack(fill="x", pady=10, padx=10)

    ctk.CTkLabel(
        display_card, text="Display Settings", font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=(15, 10), padx=20, anchor="w")

    anim_var = ctk.BooleanVar(value=bool(shared_vars.enable_animations.value))

    def toggle_animations():
        shared_vars.enable_animations.value = int(anim_var.get())
        save_callback()

    ctk.CTkCheckBox(
        display_card, text="Enable Animations",
        variable=anim_var, command=toggle_animations, font=UIStyle.BODY_FONT,
    ).pack(pady=5, padx=20, anchor="w")

    ctk.CTkLabel(display_card, text="", font=UIStyle.SMALL_FONT).pack(
        pady=(0, 10)
    )

    # ══════════════════════════════════════════════════════════
    #  Theme Selection
    # ══════════════════════════════════════════════════════════
    theme_card = CardFrame(scroll_frame)
    theme_card.pack(fill="x", pady=10, padx=10)

    ctk.CTkLabel(
        theme_card, text="Theme", font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=(15, 10), padx=20, anchor="w")

    available_themes = load_available_themes(base_path)
    current_theme = config.get("Settings", {}).get("appearance_mode", "Dark")

    theme_var = ctk.StringVar(value=current_theme)

    def apply_theme(choice):
        config["Settings"]["appearance_mode"] = choice
        save_callback()
        if restart_callback:
            restart_callback(choice)

    theme_menu = ctk.CTkOptionMenu(
        theme_card,
        variable=theme_var,
        values=list(available_themes.keys()),
        command=apply_theme,
        font=UIStyle.BODY_FONT,
        fg_color=UIStyle.OPTION_MENU_FG_COLOR,
        button_color=UIStyle.OPTION_MENU_BUTTON_COLOR,
        button_hover_color=UIStyle.OPTION_MENU_BUTTON_HOVER_COLOR,
        dropdown_fg_color=UIStyle.DROPDOWN_FG_COLOR,
        dropdown_hover_color=UIStyle.DROPDOWN_HOVER_COLOR,
        dropdown_text_color=UIStyle.DROPDOWN_TEXT_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    theme_menu.pack(pady=(0, 15), padx=20, anchor="w")

    # ══════════════════════════════════════════════════════════
    #  Uploader Configuration
    # ══════════════════════════════════════════════════════════
    uploader_card = CardFrame(scroll_frame)
    uploader_card.pack(fill="x", pady=10, padx=10)

    ctk.CTkLabel(
        uploader_card, text="Uploader Configuration",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=(15, 5), padx=20, anchor="w")

    ctk.CTkLabel(
        uploader_card,
        text="Tune upload and scrape performance. "
             "Changes take effect on the next uploader run.",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    ).pack(padx=20, anchor="w")

    # Load current uploader config
    up_cfg = config.get("Uploader", {})

    grid = ctk.CTkFrame(uploader_card, fg_color="transparent")
    grid.pack(fill="x", padx=20, pady=(10, 5))

    workers_entry = _make_setting_row(
        grid, "Upload Workers:", up_cfg.get("max_workers", 2),
        "Parallel upload threads", row=0,
    )
    tex_workers_entry = _make_setting_row(
        grid, "Texture Workers:", up_cfg.get("tex_workers", 8),
        "Parallel texture fetch threads", row=1,
    )
    cdn_entry = _make_setting_row(
        grid, "CDN Warmup (s):", up_cfg.get("cdn_warmup", 60),
        "Wait time before scraping", row=2,
    )
    mod_limit_entry = _make_setting_row(
        grid, "Moderation Limit:", up_cfg.get("mod_limit", 1),
        "Stop after N moderated frames", row=3,
    )
    watch_entry = _make_setting_row(
        grid, "Watch Timeout (s):", up_cfg.get("watch_timeout", 30),
        "Wait for new frames before stopping", row=4,
    )

    save_status = ctk.CTkLabel(
        uploader_card, text="",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    save_status.pack(padx=20, anchor="w")

    def _save_uploader_settings():
        """Validate and save uploader settings."""
        try:
            vals = {
                "max_workers": max(1, int(workers_entry.get())),
                "tex_workers": max(1, int(tex_workers_entry.get())),
                "cdn_warmup": max(0, int(cdn_entry.get())),
                "mod_limit": max(1, int(mod_limit_entry.get())),
                "watch_timeout": max(5, int(watch_entry.get())),
            }
        except ValueError:
            save_status.configure(
                text="⚠ Invalid value — use whole numbers only",
                text_color="#f44336",
            )
            return

        config["Uploader"] = vals
        save_callback()
        save_status.configure(
            text="✓ Saved", text_color="#4caf50",
        )
        # Clear the message after 3 seconds
        parent.after(3000, lambda: save_status.configure(text=""))

    btn_row = ctk.CTkFrame(uploader_card, fg_color="transparent")
    btn_row.pack(padx=20, pady=(5, 15), anchor="w")

    ctk.CTkButton(
        btn_row, text="Save Uploader Settings",
        command=_save_uploader_settings,
        width=180, height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="left", padx=(0, 10))

    def _reset_defaults():
        workers_entry.delete(0, "end"); workers_entry.insert(0, "2")
        tex_workers_entry.delete(0, "end"); tex_workers_entry.insert(0, "8")
        cdn_entry.delete(0, "end"); cdn_entry.insert(0, "60")
        mod_limit_entry.delete(0, "end"); mod_limit_entry.insert(0, "1")
        watch_entry.delete(0, "end"); watch_entry.insert(0, "30")
        _save_uploader_settings()

    ctk.CTkButton(
        btn_row, text="Reset Defaults",
        command=_reset_defaults,
        width=120, height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color="transparent", hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        text_color=UIStyle.TEXT_SECONDARY_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="left")
