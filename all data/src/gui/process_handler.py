"""
process_handler.py  —  Game logic removed.
All public functions preserved so the UI compiles unchanged.
"""
import os
import logging
from src.audio_manager import AudioManager
from src.common import BASE_PATH

logger = logging.getLogger("gui_launcher")

process           = None
exp_process       = None
threads_process   = None
battle_process    = None
battlepass_process = None
extractor_process = None
function_process_list = []
game_launcher_process = None
current_shared_vars   = None

AudioManager().initialize(BASE_PATH)

def is_any_process_running():
    return False

def get_running_process_name():
    return None

def start_mirror_dungeon(shared_vars, runs=1):
    logger.info("start_mirror_dungeon called (stub — no game logic)")
    return False

def start_exp_luxcavation(shared_vars, runs=None, stage=None):
    logger.info("start_exp_luxcavation called (stub — no game logic)")
    return False

def start_thread_luxcavation(shared_vars, runs=None, difficulty=None):
    logger.info("start_thread_luxcavation called (stub — no game logic)")
    return False

def start_battlepass_collection():
    logger.info("start_battlepass_collection called (stub — no game logic)")
    return False

def start_extraction():
    logger.info("start_extraction called (stub — no game logic)")
    return False

def start_game_launcher():
    logger.info("start_game_launcher called (stub — no game logic)")
    return False

def start_battle(base_path, python_cmd):
    logger.info("start_battle called (stub — no game logic)")

def call_function(function_name, base_path, python_cmd):
    logger.info(f"call_function({function_name!r}) called (stub — no game logic)")

def terminate_functions():
    global function_process_list
    function_process_list.clear()

def cleanup_processes():
    global process, exp_process, threads_process, battle_process
    global function_process_list, game_launcher_process, battlepass_process
    global extractor_process, current_shared_vars
    terminate_functions()
    vol = 0.5
    if current_shared_vars and hasattr(current_shared_vars, "audio_volume"):
        vol = current_shared_vars.audio_volume.value
    AudioManager().play_sound("off", vol)
