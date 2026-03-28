from multiprocessing import Value

class SharedVars:
    def __init__(self):
        self.x_offset = Value('i', 0)
        self.y_offset = Value('i', 0)
        self.enable_animations = Value('b', True)
        self.audio_volume = Value('f', 0.5)
        self.disable_audio = Value('b', False)
