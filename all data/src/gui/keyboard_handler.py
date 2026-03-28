import threading
import time
import keyboard
import logging

logger = logging.getLogger("gui_launcher")

class KeyboardHandler(threading.Thread):
    def __init__(self, callbacks, config):
        super().__init__()
        self.callbacks = callbacks
        self.config = config
        self.running = True
        self.daemon = True

    def run(self):
        self.register_shortcuts()
        while self.running:
            time.sleep(0.5)

    def register_shortcuts(self):
        """Register global hotkeys from config"""
        try:
            keyboard.unhook_all()

            if 'stop_all' in self.callbacks:
                keyboard.add_hotkey('F2', self.callbacks['stop_all'])

            shortcuts = self.config.get('Shortcuts', {})

            for key, hotkey in shortcuts.items():
                if hotkey and key in self.callbacks:
                    try:
                        keyboard.add_hotkey(hotkey, self.callbacks[key])
                    except Exception as e:
                        logger.error(f"Failed to register hotkey {hotkey} for {key}: {e}")

        except Exception as e:
            logger.error(f"Failed to register keyboard shortcuts: {e}")

    def stop(self):
        self.running = False
        keyboard.unhook_all()

    def update_shortcuts(self):
        self.register_shortcuts()
