import os
import customtkinter as ctk
import logging
from src.gui.styles import UIStyle


class UIUpdater:
    def __init__(self, root, ui_context, shared_vars, commands, base_path, sidebar):
        self.root = root
        self.ui_context = ui_context
        self.shared_vars = shared_vars
        self.commands = commands
        self.base_path = base_path
        self.sidebar = sidebar
        self.last_stats_mtime = 0

    def check_processes(self):
        """No game processes to check — show idle status."""
        try:
            if 'status_label' in self.ui_context and self.ui_context['status_label']:
                if self.ui_context['status_label'].cget("text") != "Idle":
                    self.ui_context['status_label'].configure(text="Idle", text_color=UIStyle.TEXT_SECONDARY_COLOR)
                    if 'status_indicator' in self.ui_context:
                        self.ui_context['status_indicator'].configure(text_color="#4caf50")
        except Exception as e:
            logging.getLogger("gui_launcher").error(f"Error in UI update loop: {e}")

        self.root.after(1000, self.check_processes)

    def update_compact_status(self):
        """Update status label in compact mode."""
        if 'compact_status_label' in self.ui_context and self.ui_context['compact_status_label']:
            if self.ui_context['compact_status_label'].winfo_ismapped():
                self.ui_context['compact_status_label'].configure(text="Idle", text_color=UIStyle.TEXT_SECONDARY_COLOR)

                if 'compact_stop_btn' in self.ui_context and self.ui_context['compact_stop_btn']:
                    if self.ui_context['compact_stop_btn'].winfo_ismapped():
                        self.ui_context['compact_stop_btn'].pack_forget()

        self.root.after(1000, self.update_compact_status)

    def check_stats_update(self):
        """Check if stats file has changed and reload stats tab."""
        if self.sidebar.current_page == "Statistics":
            try:
                stats_path = os.path.join(self.base_path, "config", "stats.json")
                if os.path.exists(stats_path):
                    current_mtime = os.path.getmtime(stats_path)
                    if current_mtime != self.last_stats_mtime:
                        self.last_stats_mtime = current_mtime
                        self.commands['load_statistics_tab']()
            except Exception:
                pass
        self.root.after(2000, self.check_stats_update)

    def check_chain_status(self):
        """No chain automation — no-op loop."""
        self.root.after(1000, self.check_chain_status)
