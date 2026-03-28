import os
import logging
import customtkinter as ctk
from tkinter import messagebox
from src.gui.styles import UIStyle
from src.gui.components import CardFrame
from src.gui.utils import format_log_line_with_time_ago
from src.gui.log_handler import OptimizedLogHandler
import common

def load_logs_tab(parent, log_filename, log_modules, config, save_callback, root):
    """Load and render the logs tab"""
    for widget in parent.winfo_children():
        widget.destroy()

    filter_card = CardFrame(parent)
    filter_card.pack(fill="x", padx=10, pady=(10, 5))

    filter_header = ctk.CTkFrame(filter_card, fg_color="transparent")
    filter_header.pack(fill="x", pady=(10, 5), padx=10)
    
    ctk.CTkLabel(filter_header, text="Log Filters", font=UIStyle.SUBHEADER_FONT).pack(side="left")

    toggles = ctk.CTkFrame(filter_header, fg_color="transparent")
    toggles.pack(side="right", padx=10)

    clean_logs_var = ctk.BooleanVar(value=config['Settings'].get('clean_logs', True))
    
    def toggle_clean_logs():
        config['Settings']['clean_logs'] = clean_logs_var.get()
        common.CLEAN_LOGS_ENABLED = clean_logs_var.get()
        save_callback()
        load_log_file(reload_all=True)

    ctk.CTkLabel(toggles, text="Clean Logs", font=UIStyle.SMALL_FONT).grid(row=0, column=0, padx=(0,2), sticky="e")
    ctk.CTkSwitch(toggles, text="", variable=clean_logs_var, command=toggle_clean_logs, font=UIStyle.SMALL_FONT).grid(row=0, column=1, padx=(0,10))

    filter_frame = ctk.CTkFrame(filter_card, fg_color="transparent")
    filter_frame.pack(fill="x", padx=10, pady=5)

    log_filters = {}
    module_filters = {}

    levels = ["DEBUG", "INFO", "WARNING", "ERROR"]
    for level in levels:
        var = ctk.BooleanVar(value=(level != "DEBUG"))
        log_filters[level] = var
        ctk.CTkCheckBox(filter_frame, text=level, variable=var, font=UIStyle.SMALL_FONT, 
                        command=lambda: load_log_file(reload_all=True)).pack(side="left", padx=5)

    module_frame = ctk.CTkFrame(filter_card, fg_color="transparent")
    module_frame.pack(fill="x", padx=10, pady=(0, 10))

    for module_name in log_modules:
        var = ctk.BooleanVar(value=True)
        module_filters[module_name] = var
        ctk.CTkCheckBox(module_frame, text=module_name, variable=var, font=UIStyle.SMALL_FONT,
                        command=lambda: load_log_file(reload_all=True)).pack(side="left", padx=5)

    log_text = ctk.CTkTextbox(parent, font=("Consolas", 11), fg_color="#0a0a0a", text_color="#d0d0d0", corner_radius=0)
    log_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    log_text.configure(state="disabled")

    log_handler = OptimizedLogHandler(log_text, log_filters, module_filters, log_modules)
    logging.getLogger().addHandler(log_handler)

    def load_log_file(reload_all=False):
        log_text.configure(state="normal")
        log_text.delete("1.0", "end")
        
        if os.path.exists(log_filename):
            try:
                with open(log_filename, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()[-500:]
                
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    show = True
                    for level in levels:
                        if f"| {level} |" in line and not log_filters[level].get():
                            show = False
                            break
                    
                    if show and common.CLEAN_LOGS_ENABLED and "| DIRTY" in line:
                        show = False
                    
                    if show:
                        display_line = line.replace(" | DIRTY", "")
                        formatted = format_log_line_with_time_ago(display_line)
                        log_text.insert("end", formatted + "\n")
                
            except Exception as e:
                log_text.insert("end", f"Error loading log file: {e}\n")
        
        log_text.see("end")
        log_text.configure(state="disabled")

    load_log_file()

    btn_frame = ctk.CTkFrame(parent, fg_color="transparent")
    btn_frame.pack(fill="x", padx=10, pady=(0, 10))
    
    ctk.CTkButton(btn_frame, text="Refresh", command=lambda: load_log_file(reload_all=True), 
                  height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
                  fg_color=UIStyle.BUTTON_COLOR, hover_color=UIStyle.BUTTON_HOVER_COLOR,
                  border_width=1, border_color=UIStyle.BUTTON_BORDER_COLOR,
                  corner_radius=UIStyle.CORNER_RADIUS).pack(side="left", padx=5)
    
    def clear_logs():
        if messagebox.askyesno("Clear Logs", "Are you sure you want to clear the log file?"):
            try:
                with open(log_filename, 'w') as f:
                    f.write("")
                load_log_file(reload_all=True)
            except Exception as e:
                messagebox.showerror("Error", f"Failed to clear logs: {e}")
    
    ctk.CTkButton(btn_frame, text="Clear Logs", command=clear_logs, 
                  height=UIStyle.BUTTON_HEIGHT, font=UIStyle.BODY_FONT,
                  fg_color="#c42b1c", hover_color="#8f1f14",
                  corner_radius=UIStyle.CORNER_RADIUS).pack(side="left", padx=5)
