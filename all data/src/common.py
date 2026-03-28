"""
common.py  —  Lightweight stub.
All heavy game automation (cv2, interception, mss, numpy) removed.
UI-facing helpers kept intact.
"""
import os, sys, time, logging, threading, urllib.request, urllib.error
from logging.handlers import RotatingFileHandler

# ── Path helpers ──────────────────────────────────────────────────────────────
def get_base_path():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    folder = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(folder) if os.path.basename(folder) == "src" else folder

BASE_PATH = get_base_path()

# ── Logging setup ─────────────────────────────────────────────────────────────
CLEAN_LOGS_ENABLED = True

LOG_DIR = os.path.join(BASE_PATH, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILENAME = os.path.join(LOG_DIR, "Logs.log")

class NoMillisecondsFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        return time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(record.created))
    def format(self, record):
        formatted = super().format(record)
        if getattr(record, "dirty", False):
            formatted += " | DIRTY"
        return formatted

_handler = RotatingFileHandler(LOG_FILENAME, maxBytes=1*1024*1024, backupCount=1, encoding="utf-8")
_fmt = NoMillisecondsFormatter(
    fmt="%(asctime)s | %(name)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s",
    datefmt="%d/%m/%Y %H:%M:%S"
)
_handler.setFormatter(_fmt)
logging.getLogger().handlers.clear()
logging.basicConfig(level=logging.DEBUG, handlers=[_handler], force=True)
logger = logging.getLogger(__name__)

# Async logging compat stubs (logger.py may provide real ones)
try:
    from logger import AsyncDirtyLogger, start_async_logging, set_logging_enabled, is_logging_enabled
    _ASYNC = True
except ImportError:
    _ASYNC = False
    def set_logging_enabled(enabled): pass
    def is_logging_enabled(): return True

def initialize_async_logging():
    if _ASYNC:
        try:
            start_async_logging(LOG_FILENAME)
            return True
        except Exception as e:
            logger.warning(f"Async logging init failed: {e}")
    return False

# ── Monitor helpers ───────────────────────────────────────────────────────────
_game_monitor = 1

def list_available_monitors():
    """Return a list of connected monitors. Uses mss if available."""
    try:
        from mss import mss as _mss
        with _mss() as sct:
            result = []
            for i, m in enumerate(sct.monitors):
                if i == 0:
                    continue
                result.append({"index": i, "left": m["left"], "top": m["top"],
                                "width": m["width"], "height": m["height"]})
            return result if result else [{"index": 1, "left": 0, "top": 0, "width": 1920, "height": 1080}]
    except Exception:
        return [{"index": 1, "left": 0, "top": 0, "width": 1920, "height": 1080}]

def set_game_monitor(monitor_index):
    global _game_monitor
    _game_monitor = monitor_index
    try:
        import src.shared_vars as sv
        sv.game_monitor = monitor_index
    except Exception:
        pass
    return monitor_index

def get_resolution(monitor_index=None):
    monitors = list_available_monitors()
    idx = (monitor_index or _game_monitor) - 1
    if idx < 0 or idx >= len(monitors):
        idx = 0
    m = monitors[idx]
    return m["width"], m["height"]

# ── Coordinate scaling (passthrough — no game running) ────────────────────────
MONITOR_WIDTH  = 1920
MONITOR_HEIGHT = 1080
EXPECTED_WIDTH  = 1920
EXPECTED_HEIGHT = 1080

def scale_coordinates_1080p(x, y): return (x, y)
def scale_coordinates_1440p(x, y): return (x, y)
def scale_x(x, *, padding=True):   return x
def scale_y(y, *, padding=True):   return y
def scale_x_1080p(x, *, padding=True): return x
def scale_y_1080p(y, *, padding=True): return y
def scale_offset_1080p(x, y):      return (x, y)
def scale_offset_1440p(x, y):      return (x, y)
def uniform_scale_coordinates(x, y):       return (x, y)
def uniform_scale_coordinates_1080p(x, y): return (x, y)

# ── Network ───────────────────────────────────────────────────────────────────
def check_internet_connection(timeout=5):
    try:
        urllib.request.urlopen("https://www.google.com", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError):
        return False
