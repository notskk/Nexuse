import os
import json
import logging
from threading import Lock

def get_base_path():
    import sys
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    else:
        folder_path = os.path.dirname(os.path.abspath(__file__))
        if os.path.basename(folder_path) == 'src':
            return os.path.dirname(folder_path)
        return folder_path

BASE_PATH = get_base_path()

logger = logging.getLogger(__name__)

_config_cache = {}
_cache_lock = Lock()

class ConfigCache:
    
    @staticmethod
    def get_config(config_name):
        with _cache_lock:
            if config_name not in _config_cache:
                ConfigCache._load_config(config_name)
            return _config_cache.get(config_name, {})
    
    @staticmethod
    def _load_config(config_name):
        try:
            import sys as _sys
            config_path = os.path.join(BASE_PATH, "config", f"{config_name}.json")
            if not os.path.exists(config_path) and getattr(_sys, 'frozen', False):
                config_path = os.path.join(_sys._MEIPASS, "config", f"{config_name}.json")
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    _config_cache[config_name] = json.load(f)
                logger.debug(f"Loaded config {config_name} into cache")
            else:
                _config_cache[config_name] = {}
                logger.debug(f"Config {config_name} not found, using empty dict")
        except Exception as e:
            logger.error(f"Error loading config {config_name}: {e}")
            _config_cache[config_name] = {}
    
    @staticmethod
    def reload_config(config_name):
        with _cache_lock:
            if config_name in _config_cache:
                del _config_cache[config_name]
            ConfigCache._load_config(config_name)
    
    @staticmethod
    def reload_all():
        with _cache_lock:
            config_names = list(_config_cache.keys())
            _config_cache.clear()
            for config_name in config_names:
                ConfigCache._load_config(config_name)
    
    @staticmethod
    def preload_all_configs():
        config_files = ["gui_config"]
        with _cache_lock:
            for config_name in config_files:
                if config_name not in _config_cache:
                    ConfigCache._load_config(config_name)
        logger.info(f"Preloaded {len(config_files)} config files")


def _get_gui_values():
    return {
        'x_offset': 0,
        'y_offset': 0,
        'enable_animations': True,
        'audio_volume': 0.5,
        'disable_audio': False,
    }

def _load_shared_vars():
    logger.info("Loading shared variables from configuration")

    gui_values = _get_gui_values()
    
    try:
        config_path = os.path.join(BASE_PATH, "config", "gui_config.json")
        
        if os.path.exists(config_path):
            logger.debug(f"Loading configuration file: {config_path}")
            with open(config_path, 'r') as f:
                config = json.load(f)

            shared_vars_data = config.get('SharedVars', {})
            if not shared_vars_data:
                settings_data = config.get('Settings', {})
                shared_vars_data = {key: settings_data.get(key, gui_values[key]) 
                                  for key in gui_values.keys() if key in settings_data}

            for var_name, gui_value in gui_values.items():
                value = shared_vars_data.get(var_name, gui_value)
                globals()[var_name] = value
            
            logger.info("Configuration loaded successfully")
                
        else:
            logger.warning(f"GUI config file not found at {config_path}, using GUI values")
            for var_name, gui_value in gui_values.items():
                globals()[var_name] = gui_value
                
    except Exception as e:
        logger.error(f"Error loading shared variables from config: {e}")
        for var_name, gui_value in gui_values.items():
            globals()[var_name] = gui_value

def _update_all_exports():
    global __all__
    config_vars = list(_get_gui_values().keys())
    __all__ = config_vars + ['reload_shared_vars']

def reload_shared_vars():
    _load_shared_vars()

_load_shared_vars()
_update_all_exports()

ConfigCache.preload_all_configs()
