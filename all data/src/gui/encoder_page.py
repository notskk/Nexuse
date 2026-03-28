import os
import tempfile
import logging
import customtkinter as ctk
from tkinter import filedialog
from src.gui.styles import UIStyle
from src.gui.components import CardFrame

logger = logging.getLogger(__name__)


def load_encoder_page(parent, base_path):
    """Load and render the Encoder / Decoder tab."""
    for widget in parent.winfo_children():
        widget.destroy()

    scroll_frame = ctk.CTkScrollableFrame(
        parent, corner_radius=0, fg_color="transparent"
    )
    scroll_frame.pack(fill="both", expand=True)

    # ── Page header ──────────────────────────────────────────
    hdr_row = ctk.CTkFrame(scroll_frame, fg_color="transparent")
    hdr_row.pack(fill="x", padx=20, pady=(20, 4))

    ctk.CTkLabel(
        hdr_row, text="Encoder / Decoder",
        font=UIStyle.HEADER_FONT,
    ).pack(side="left")

    status_label = ctk.CTkLabel(
        hdr_row, text="Ready",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    )
    status_label.pack(side="right", padx=10)

    ctk.CTkLabel(
        scroll_frame,
        text="Encode JSON to Base64+zstd  or  Decode Base64+zstd back to JSON",
        font=UIStyle.SMALL_FONT, text_color=UIStyle.TEXT_SECONDARY_COLOR,
    ).pack(padx=22, anchor="w", pady=(0, 8))

    # ══════════════════════════════════════════════════════════
    #  Main card  –  side-by-side  Input  |  Actions  |  Output
    # ══════════════════════════════════════════════════════════
    card = CardFrame(scroll_frame)
    card.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    panes = ctk.CTkFrame(card, fg_color="transparent")
    panes.pack(fill="both", expand=True, padx=12, pady=12)
    panes.columnconfigure(0, weight=1)   # input
    panes.columnconfigure(1, weight=0)   # action buttons
    panes.columnconfigure(2, weight=1)   # output
    panes.rowconfigure(1, weight=1)

    # ── Input pane ───────────────────────────────────────────
    in_hdr = ctk.CTkFrame(panes, fg_color="transparent")
    in_hdr.grid(row=0, column=0, sticky="ew", pady=(0, 4))

    ctk.CTkLabel(
        in_hdr, text="Input", font=UIStyle.SUBHEADER_FONT,
    ).pack(side="left")

    def _load_file():
        path = filedialog.askopenfilename(
            filetypes=[
                ("All Files", "*.*"),
                ("Text", "*.txt"),
                ("JSON", "*.json"),
            ]
        )
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                input_box.delete("1.0", "end")
                input_box.insert("1.0", content)
                status_label.configure(
                    text=f"Loaded {os.path.basename(path)}",
                    text_color="#4caf50",
                )
            except Exception as exc:
                status_label.configure(
                    text=f"Load failed: {exc}", text_color="#f44336"
                )

    ctk.CTkButton(
        in_hdr, text="Load File", command=_load_file,
        width=72, height=26, font=UIStyle.SMALL_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="right")

    input_box = ctk.CTkTextbox(
        panes, height=260,
        font=("Consolas", 11),
        fg_color=UIStyle.INPUT_BG_COLOR,
        text_color=UIStyle.TEXT_COLOR,
        border_color=UIStyle.BORDER_COLOR,
        border_width=1,
        corner_radius=UIStyle.CORNER_RADIUS,
        wrap="none",
    )
    input_box.grid(row=1, column=0, sticky="nsew")

    # ── Centre action column ─────────────────────────────────
    action_col = ctk.CTkFrame(panes, fg_color="transparent", width=90)
    action_col.grid(row=1, column=1, padx=10, sticky="ns")
    action_col.grid_propagate(False)

    # Spacer to vertically centre the buttons
    ctk.CTkFrame(action_col, fg_color="transparent", height=50).pack()

    def _run(mode):
        input_text = input_box.get("1.0", "end-1c").strip()
        if not input_text:
            status_label.configure(
                text="Nothing to process", text_color="#ff9800"
            )
            return

        try:
            from src.zstd_tool import encode_file, decode_file
        except ImportError as exc:
            status_label.configure(
                text="zstandard missing -- pip install zstandard",
                text_color="#f44336",
            )
            logger.error("Import error: %s", exc)
            return

        status_label.configure(
            text=f"{mode}ing...", text_color="#ff9800"
        )

        tmp_in_path = None
        tmp_out_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, encoding="utf-8"
            ) as tmp_in:
                tmp_in.write(input_text)
                tmp_in_path = tmp_in.name

            tmp_out_path = tmp_in_path + ".out"

            import io
            from contextlib import redirect_stdout
            captured = io.StringIO()
            with redirect_stdout(captured):
                if mode == "Encode":
                    encode_file(tmp_in_path, tmp_out_path)
                else:
                    decode_file(tmp_in_path, tmp_out_path)

            if os.path.exists(tmp_out_path):
                with open(tmp_out_path, "r", encoding="utf-8") as f:
                    result = f.read()
                _set_output(result)
                status_label.configure(
                    text=f"{mode}d successfully",
                    text_color="#4caf50",
                )
            else:
                _set_output(captured.getvalue() or "No output generated.")
                status_label.configure(
                    text="No output", text_color="#ff9800"
                )
        except Exception as exc:
            logger.error("Encoder error: %s", exc)
            status_label.configure(
                text=f"Error: {exc}", text_color="#f44336"
            )
        finally:
            for p in (tmp_in_path, tmp_out_path):
                if p:
                    try:
                        os.unlink(p)
                    except OSError:
                        pass

    ctk.CTkButton(
        action_col, text="Encode  >>",
        command=lambda: _run("Encode"),
        width=80, height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(pady=(0, 6))

    ctk.CTkButton(
        action_col, text="<<  Decode",
        command=lambda: _run("Decode"),
        width=80, height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(pady=(0, 14))

    def _clear_all():
        input_box.delete("1.0", "end")
        output_box.configure(state="normal")
        output_box.delete("1.0", "end")
        output_box.configure(state="disabled")
        status_label.configure(
            text="Ready", text_color=UIStyle.TEXT_SECONDARY_COLOR
        )

    ctk.CTkButton(
        action_col, text="Clear",
        command=_clear_all,
        width=80, height=28, font=UIStyle.SMALL_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(pady=(0, 4))

    def _swap():
        """Move output text back to input."""
        output_box.configure(state="normal")
        text = output_box.get("1.0", "end-1c")
        output_box.configure(state="disabled")
        if text.strip():
            input_box.delete("1.0", "end")
            input_box.insert("1.0", text)
            status_label.configure(
                text="Swapped", text_color="#4caf50"
            )

    ctk.CTkButton(
        action_col, text="Swap",
        command=_swap,
        width=80, height=28, font=UIStyle.SMALL_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack()

    # ── Output pane ──────────────────────────────────────────
    out_hdr = ctk.CTkFrame(panes, fg_color="transparent")
    out_hdr.grid(row=0, column=2, sticky="ew", pady=(0, 4))

    ctk.CTkLabel(
        out_hdr, text="Output", font=UIStyle.SUBHEADER_FONT,
    ).pack(side="left")

    def _copy_output():
        text = output_box.get("1.0", "end-1c")
        if text.strip():
            parent.clipboard_clear()
            parent.clipboard_append(text)
            status_label.configure(text="Copied!", text_color="#4caf50")

    def _save_output():
        text = output_box.get("1.0", "end-1c")
        if not text.strip():
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[
                ("Text", "*.txt"),
                ("JSON", "*.json"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(text)
                status_label.configure(text="Saved!", text_color="#4caf50")
            except Exception as exc:
                logger.error("Save error: %s", exc)
                status_label.configure(
                    text=f"Save failed: {exc}", text_color="#f44336"
                )

    ctk.CTkButton(
        out_hdr, text="Save", command=_save_output,
        width=54, height=26, font=UIStyle.SMALL_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="right", padx=(4, 0))

    ctk.CTkButton(
        out_hdr, text="Copy", command=_copy_output,
        width=54, height=26, font=UIStyle.SMALL_FONT,
        fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
        border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
        corner_radius=UIStyle.CORNER_RADIUS,
    ).pack(side="right")

    output_box = ctk.CTkTextbox(
        panes, height=260,
        font=("Consolas", 11),
        fg_color=UIStyle.INPUT_BG_COLOR,
        text_color=UIStyle.TEXT_COLOR,
        border_color=UIStyle.BORDER_COLOR,
        border_width=1,
        corner_radius=UIStyle.CORNER_RADIUS,
        wrap="none",
    )
    output_box.grid(row=1, column=2, sticky="nsew")
    output_box.configure(state="disabled")

    def _set_output(text):
        output_box.configure(state="normal")
        output_box.delete("1.0", "end")
        output_box.insert("1.0", text)
        output_box.configure(state="disabled")
