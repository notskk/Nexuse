"""
chain_automation.py  —  Game logic removed.
All public functions preserved so the UI compiles unchanged.
"""
import logging
import src.gui.process_handler as process_handler

logger = logging.getLogger("gui_launcher")

chain_running = False
chain_queue = []
current_chain_step = 0
battlepass_process = None
battlepass_completed = False

def start_chain_automation(ui_context, shared_vars):
    global chain_running
    if chain_running:
        stop_chain_automation(ui_context)
        return
    logger.info("start_chain_automation called (stub — no game logic)")
    if "chain_status_label" in ui_context:
        ui_context["chain_status_label"].configure(text="Chain Status: No automation configured")

def stop_chain_automation(ui_context):
    global chain_running
    chain_running = False
    process_handler.cleanup_processes()
    if ui_context and "chain_start_button" in ui_context:
        try: ui_context["chain_start_button"].after(0, lambda: ui_context["chain_start_button"].configure(text="Start Chain"))
        except: pass
    if ui_context and "chain_status_label" in ui_context:
        try: ui_context["chain_status_label"].after(0, lambda: ui_context["chain_status_label"].configure(text="Chain Status: Stopped"))
        except: pass

def run_next_chain_step(ui_context, shared_vars):
    pass

def start_reward_collection(ui_context):
    pass

def check_chain_status(root, ui_context, shared_vars):
    pass

def finish_chain(ui_context):
    global chain_running
    chain_running = False
    if "chain_start_button" in ui_context:
        ui_context["chain_start_button"].configure(text="Start Chain")
    if "chain_status_label" in ui_context:
        ui_context["chain_status_label"].configure(text="Chain Status: Completed")
