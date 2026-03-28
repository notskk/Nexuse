import os
import json
import tkinter as tk
import customtkinter as ctk

from src.gui.styles import UIStyle
from src.gui.components import CardFrame, ModernEntry

PROFILES_FILENAME = "profiles.json"


# ── Persistence helpers ───────────────────────────────────────────────

def _profiles_path(base_path: str) -> str:
    return os.path.join(base_path, "config", PROFILES_FILENAME)


def load_profiles(base_path: str) -> dict:
    """Return the full profiles dict from disk, or a sensible default."""
    path = _profiles_path(base_path)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Ensure expected keys exist
            data.setdefault("active_profile", None)
            data.setdefault("profiles", {})
            return data
        except Exception:
            pass
    return {"active_profile": None, "profiles": {}}


def save_profiles(base_path: str, data: dict) -> None:
    os.makedirs(os.path.join(base_path, "config"), exist_ok=True)
    with open(_profiles_path(base_path), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)


def get_active_profile_env(base_path: str) -> dict:
    """
    Return a dict of env-var overrides for the active profile.
    Pass this dict into subprocess env when running the uploader.
    Returns an empty dict if no active profile is set.
    """
    data = load_profiles(base_path)
    active = data.get("active_profile")
    if not active:
        return {}
    profile = data.get("profiles", {}).get(active, {})
    env = {}
    if profile.get("api_key"):
        env["ROBLOX_API_KEY"] = profile["api_key"]
    if profile.get("user_id"):
        env["ROBLOX_USER_ID"] = str(profile["user_id"])
    if profile.get("roblosecurity"):
        cookie = profile["roblosecurity"]
        # Strip the ".ROBLOSECURITY=" prefix users may paste from devtools.
        # NOTE: do NOT strip "_|WARNING:..." — that IS part of the cookie!
        if cookie.startswith(".ROBLOSECURITY="):
            cookie = cookie[len(".ROBLOSECURITY="):]
        env["ROBLOSECURITY"] = cookie
    if profile.get("discord_webhook"):
        env["DISCORD_WEBHOOK_URL"] = profile["discord_webhook"]
    return env


# ── Page loader ───────────────────────────────────────────────────────

def load_profiles_page(parent, base_path: str) -> None:
    """Render the Profiles tab inside *parent*."""
    for w in parent.winfo_children():
        w.destroy()

    # ── State ──────────────────────────────────────────────
    _data: dict = load_profiles(base_path)   # live copy
    _selected: list = [None]                  # currently selected profile name

    # ── Outer scroll container ──────────────────────────────
    scroll = ctk.CTkScrollableFrame(parent, corner_radius=0, fg_color="transparent")
    scroll.pack(fill="both", expand=True)

    ctk.CTkLabel(
        scroll, text="Profiles",
        font=UIStyle.HEADER_FONT,
    ).pack(pady=(20, 4), anchor="w", padx=20)

    ctk.CTkLabel(
        scroll,
        text="Store your Roblox credentials in named profiles instead of a .env file.\n"
             "The active profile is injected automatically when the uploader runs.",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
        justify="left",
    ).pack(anchor="w", padx=20, pady=(0, 14))

    # ── Two-column layout ───────────────────────────────────
    columns = ctk.CTkFrame(scroll, fg_color="transparent")
    columns.pack(fill="both", expand=True, padx=10, pady=4)
    columns.columnconfigure(0, weight=1, minsize=190)
    columns.columnconfigure(1, weight=3)

    # ══════════════════════════════════════════════════════
    #  LEFT: Profile List
    # ══════════════════════════════════════════════════════
    list_card = CardFrame(columns)
    list_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

    ctk.CTkLabel(
        list_card, text="Saved Profiles",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(pady=(15, 6), padx=14, anchor="w")

    list_box = ctk.CTkScrollableFrame(
        list_card, fg_color=UIStyle.INPUT_BG_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    list_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ── New profile button ──────────────────────────────────
    new_btn = ctk.CTkButton(
        list_card, text="＋  New Profile",
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    new_btn.pack(fill="x", padx=10, pady=(0, 12))

    # ══════════════════════════════════════════════════════
    #  RIGHT: Edit Form
    # ══════════════════════════════════════════════════════
    form_card = CardFrame(columns)
    form_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)

    form_hdr_row = ctk.CTkFrame(form_card, fg_color="transparent")
    form_hdr_row.pack(fill="x", padx=15, pady=(15, 4))

    form_title = ctk.CTkLabel(
        form_hdr_row, text="New Profile",
        font=UIStyle.SUBHEADER_FONT,
    )
    form_title.pack(side="left")

    active_badge = ctk.CTkLabel(
        form_hdr_row, text="",
        font=UIStyle.SMALL_FONT,
        text_color="#4caf50",
    )
    active_badge.pack(side="right")

    # ── Form fields ─────────────────────────────────────────
    fields_frame = ctk.CTkFrame(form_card, fg_color="transparent")
    fields_frame.pack(fill="x", padx=15, pady=4)

    def _make_field(parent_frame, label: str, row: int,
                    show: str = "", placeholder: str = "") -> ctk.CTkEntry:
        ctk.CTkLabel(
            parent_frame, text=label, font=UIStyle.BODY_FONT,
            text_color=UIStyle.TEXT_SECONDARY_COLOR, anchor="w",
        ).grid(row=row, column=0, sticky="w", pady=(8, 2), padx=(0, 12))
        entry = ModernEntry(parent_frame, show=show)
        if placeholder:
            entry.configure(placeholder_text=placeholder)
        entry.grid(row=row, column=1, sticky="ew", pady=(8, 2))
        parent_frame.columnconfigure(1, weight=1)
        return entry

    e_name      = _make_field(fields_frame, "Profile Name",      0, placeholder="e.g. MyAccount")
    e_api_key   = _make_field(fields_frame, "Roblox API Key",    1, show="•", placeholder="Open-Cloud API key")
    e_user_id   = _make_field(fields_frame, "Roblox User ID",    2, placeholder="Numeric user ID")
    e_rbxsec    = _make_field(fields_frame, ".ROBLOSECURITY",     3, show="•", placeholder="Browser cookie value")
    e_webhook   = _make_field(fields_frame, "Discord Webhook",   4, placeholder="https://discord.com/api/webhooks/…  (optional)")

    # Show/hide toggles for masked fields
    def _make_toggle(entry: ctk.CTkEntry, row: int) -> None:
        _visible = [False]
        def _toggle():
            _visible[0] = not _visible[0]
            entry.configure(show="" if _visible[0] else "•")
            toggle_btn.configure(text="🙈 Hide" if _visible[0] else "👁 Show")
        toggle_btn = ctk.CTkButton(
            fields_frame,
            text="👁 Show",
            width=70, height=28,
            font=UIStyle.SMALL_FONT,
            fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
            border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
            corner_radius=UIStyle.CORNER_RADIUS,
            command=_toggle,
        )
        toggle_btn.grid(row=row, column=2, padx=(6, 0), pady=(8, 2))

    _make_toggle(e_api_key, 1)
    _make_toggle(e_rbxsec,  3)

    # ── Status label ────────────────────────────────────────
    status_lbl = ctk.CTkLabel(
        form_card, text="",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    status_lbl.pack(padx=15, anchor="w", pady=(6, 0))

    # ── Action buttons ──────────────────────────────────────
    btn_row = ctk.CTkFrame(form_card, fg_color="transparent")
    btn_row.pack(fill="x", padx=15, pady=(8, 18))

    def _status(msg: str, color: str = UIStyle.TEXT_SECONDARY_COLOR):
        status_lbl.configure(text=msg, text_color=color)

    # ── Core logic ───────────────────────────────────────────

    def _refresh_list():
        """Rebuild the profile list buttons."""
        for w in list_box.winfo_children():
            w.destroy()
        active = _data.get("active_profile")
        profiles = _data.get("profiles", {})
        if not profiles:
            ctk.CTkLabel(
                list_box, text="No profiles yet",
                font=UIStyle.SMALL_FONT,
                text_color=UIStyle.TEXT_SECONDARY_COLOR,
            ).pack(pady=12)
            return
        for name in profiles:
            is_active = (name == active)
            label_text = f"✔ {name}" if is_active else f"   {name}"
            btn = ctk.CTkButton(
                list_box,
                text=label_text,
                anchor="w",
                height=36,
                font=UIStyle.BODY_FONT,
                fg_color=UIStyle.BUTTON_COLOR if not is_active else "#1a3a1a",
                hover_color=UIStyle.BUTTON_HOVER_COLOR,
                text_color=("#4caf50" if is_active else UIStyle.TEXT_COLOR),
                border_width=1,
                border_color=UIStyle.BUTTON_BORDER_COLOR,
                corner_radius=UIStyle.CORNER_RADIUS,
                command=lambda n=name: _select_profile(n),
            )
            btn.pack(fill="x", pady=2, padx=4)

    def _clear_form():
        """Reset the form to 'new profile' state."""
        _selected[0] = None
        form_title.configure(text="New Profile")
        active_badge.configure(text="")
        for entry in (e_name, e_api_key, e_user_id, e_rbxsec, e_webhook):
            entry.delete(0, "end")
        _status("")

    def _select_profile(name: str):
        """Load a profile's data into the form."""
        _selected[0] = name
        profile = _data["profiles"].get(name, {})
        form_title.configure(text=name)
        active = _data.get("active_profile")
        if name == active:
            active_badge.configure(text="● Active", text_color="#4caf50")
        else:
            active_badge.configure(text="")

        for entry in (e_name, e_api_key, e_user_id, e_rbxsec, e_webhook):
            entry.delete(0, "end")

        e_name.insert(0, name)
        e_api_key.insert(0, profile.get("api_key", ""))
        e_user_id.insert(0, str(profile.get("user_id", "")))
        e_rbxsec.insert(0, profile.get("roblosecurity", ""))
        e_webhook.insert(0, profile.get("discord_webhook", ""))
        _status("")

    def _save_profile():
        name = e_name.get().strip()
        if not name:
            _status("⚠ Profile name is required.", "#f44336")
            return

        # Show warning for new profiles
        is_new = (name not in _data.get("profiles", {})
                  and _selected[0] != name)
        if is_new:
            if not _show_account_warning():
                _status("Cancelled.", UIStyle.TEXT_SECONDARY_COLOR)
                return

        api_key  = e_api_key.get().strip()
        user_id  = e_user_id.get().strip()
        rbxsec   = e_rbxsec.get().strip()
        webhook  = e_webhook.get().strip()

        # If renaming, remove old key
        old_name = _selected[0]
        if old_name and old_name != name and old_name in _data["profiles"]:
            del _data["profiles"][old_name]
            if _data.get("active_profile") == old_name:
                _data["active_profile"] = name

        _data["profiles"][name] = {
            "api_key":        api_key,
            "user_id":        user_id,
            "roblosecurity":  rbxsec,
            "discord_webhook": webhook,
        }
        _selected[0] = name
        save_profiles(base_path, _data)
        _refresh_list()
        form_title.configure(text=name)
        _status(f"✓ Profile '{name}' saved.", "#4caf50")

    def _set_active():
        name = _selected[0] or e_name.get().strip()
        if not name or name not in _data.get("profiles", {}):
            _status("⚠ Save the profile first before activating it.", "#f44336")
            return
        _data["active_profile"] = name
        save_profiles(base_path, _data)
        _refresh_list()
        active_badge.configure(text="● Active", text_color="#4caf50")
        _status(f"✓ '{name}' is now the active profile.", "#4caf50")

    def _delete_profile():
        name = _selected[0]
        if not name:
            _status("⚠ Select a profile to delete.", "#f44336")
            return
        if name in _data.get("profiles", {}):
            del _data["profiles"][name]
        if _data.get("active_profile") == name:
            _data["active_profile"] = None
        save_profiles(base_path, _data)
        _clear_form()
        _refresh_list()
        _status(f"Profile '{name}' deleted.", UIStyle.TEXT_SECONDARY_COLOR)

    def _new_profile():
        _clear_form()


    def _show_account_warning():
        """Show inline warning overlay on the form card with a 3-second countdown."""
        _result = [False]
        _done = tk.BooleanVar(value=False)
        _countdown = [3]

        # Dark overlay covers the entire form card
        warn_overlay = ctk.CTkFrame(
            form_card, fg_color="#1a0808",
            corner_radius=UIStyle.CORNER_RADIUS,
        )
        warn_overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Center content inside overlay
        inner = ctk.CTkFrame(warn_overlay, fg_color="transparent")
        inner.place(relx=0.5, rely=0.5, anchor="center")

        ctk.CTkLabel(
            inner, text="⚠️  IMPORTANT WARNING",
            font=("Segoe UI", 18, "bold"), text_color="#f44336",
        ).pack(pady=(0, 12))

        ctk.CTkLabel(
            inner,
            text="DO NOT use your main Roblox account!\n\n"
                 "This tool uploads many assets rapidly which may\n"
                 "trigger moderation or account restrictions.\n\n"
                 "Make sure your videos do NOT contain bannable\n"
                 "content (NSFW, extreme violence, copyrighted\n"
                 "material, etc).\n\n"
                 "You are responsible for what you upload.",
            font=("Segoe UI", 12),
            justify="center",
        ).pack(padx=20)

        def _agree():
            _result[0] = True
            _done.set(True)

        def _cancel():
            _done.set(True)

        agree_btn = ctk.CTkButton(
            inner, text=f"I Understand ({_countdown[0]}s)",
            state="disabled",
            fg_color=UIStyle.CARD_COLOR,
            hover_color=UIStyle.CARD_COLOR,
            text_color=UIStyle.TEXT_SECONDARY_COLOR,
            border_color=UIStyle.BORDER_COLOR,
            border_width=1,
            font=("Segoe UI", 13, "bold"),
            height=36, width=200,
            command=_agree,
        )
        agree_btn.pack(pady=(18, 8))

        cancel_btn = ctk.CTkButton(
            inner, text="Cancel",
            fg_color=UIStyle.BUTTON_COLOR,
            hover_color=UIStyle.BUTTON_HOVER_COLOR,
            border_color="#c42b1c",
            border_width=1,
            text_color="#c42b1c",
            font=("Segoe UI", 12),
            height=30, width=120,
            command=_cancel,
        )
        cancel_btn.pack()

        def _tick():
            _countdown[0] -= 1
            if _countdown[0] > 0:
                agree_btn.configure(text=f"I Understand ({_countdown[0]}s)")
                warn_overlay.after(1000, _tick)
            else:
                agree_btn.configure(
                    text="I Understand",
                    state="normal",
                    fg_color="#1a5a2e",
                    hover_color="#267a3e",
                    text_color="#4caf50",
                    border_color="#267a3e",
                )

        warn_overlay.after(1000, _tick)
        parent.wait_variable(_done)
        warn_overlay.destroy()
        return _result[0]

    # Wire buttons
    new_btn.configure(command=_new_profile)

    save_btn = ctk.CTkButton(
        btn_row, text="💾  Save",
        command=_save_profile,
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    save_btn.pack(side="left", padx=(0, 6))

    activate_btn = ctk.CTkButton(
        btn_row, text="✔  Set Active",
        command=_set_active,
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color="#1a3a1a", hover_color="#2a5a2a",
        border_width=1, border_color="#2a5a2a",
        text_color="#4caf50",
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    activate_btn.pack(side="left", padx=(0, 6))

    delete_btn = ctk.CTkButton(
        btn_row, text="🗑  Delete",
        command=_delete_profile,
        height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color="#2a0a0a", hover_color="#5a1010",
        border_width=1, border_color="#5a1010",
        text_color="#f44336",
        corner_radius=UIStyle.CORNER_RADIUS,
    )
    delete_btn.pack(side="left")

    # ── Active profile info box ─────────────────────────────
    info_card = CardFrame(scroll)
    info_card.pack(fill="x", padx=10, pady=(14, 10))

    info_hdr = ctk.CTkFrame(info_card, fg_color="transparent")
    info_hdr.pack(fill="x", padx=15, pady=(12, 4))

    ctk.CTkLabel(
        info_hdr, text="Active Profile",
        font=UIStyle.SUBHEADER_FONT,
    ).pack(side="left")

    def _refresh_active_info():
        for w in info_body.winfo_children():
            w.destroy()
        active = _data.get("active_profile")
        if not active:
            ctk.CTkLabel(
                info_body, text="No active profile — select a profile and click 'Set Active'.",
                font=UIStyle.SMALL_FONT,
                text_color=UIStyle.TEXT_SECONDARY_COLOR,
            ).pack(padx=15, pady=8, anchor="w")
            return
        profile = _data.get("profiles", {}).get(active, {})
        rows = [
            ("Name",        active),
            ("User ID",     profile.get("user_id",  "—") or "—"),
            ("API Key",     ("••••••" + profile["api_key"][-6:]) if profile.get("api_key") else "—"),
            ("ROBLOSECURITY", "set ✓" if profile.get("roblosecurity") else "not set"),
            ("Discord Webhook", "set ✓" if profile.get("discord_webhook") else "not set"),
        ]
        for label, value in rows:
            r = ctk.CTkFrame(info_body, fg_color="transparent")
            r.pack(fill="x", padx=15, pady=2)
            ctk.CTkLabel(
                r, text=f"{label}:", font=UIStyle.BODY_FONT,
                text_color=UIStyle.TEXT_SECONDARY_COLOR, width=160, anchor="w",
            ).pack(side="left")
            ctk.CTkLabel(
                r, text=value, font=UIStyle.BODY_FONT,
                text_color=UIStyle.TEXT_COLOR, anchor="w",
            ).pack(side="left")

    info_body = ctk.CTkFrame(info_card, fg_color="transparent")
    info_body.pack(fill="x", pady=(0, 12))

    # Patch _set_active and _delete_profile to also refresh info box
    _orig_set_active = _set_active
    def _set_active_refreshing():
        _orig_set_active()
        _refresh_active_info()
    activate_btn.configure(command=_set_active_refreshing)

    _orig_delete = _delete_profile
    def _delete_refreshing():
        _orig_delete()
        _refresh_active_info()
    delete_btn.configure(command=_delete_refreshing)

    # ── Initial render ──────────────────────────────────────
    _refresh_list()
    _refresh_active_info()
