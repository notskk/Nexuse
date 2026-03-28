import logging
import common

logger = logging.getLogger("gui_launcher")

def load_preferences(config, shared_vars):
    """Load settings from config into shared_vars"""
    settings = config.get("Settings", {})

    if "x_offset" in settings: shared_vars.x_offset.value = int(settings["x_offset"])
    if "y_offset" in settings: shared_vars.y_offset.value = int(settings["y_offset"])
    if "enable_animations" in settings: shared_vars.enable_animations.value = bool(settings["enable_animations"])
    if "audio_volume" in settings: shared_vars.audio_volume.value = float(settings["audio_volume"])

def setup_environment(shared_vars):
    """Initialize common settings from shared_vars"""
    try:
        logger.info("Common settings initialized")
    except Exception as e:
        logger.error(f"Error initializing common settings: {e}")
