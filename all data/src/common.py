"""
common.py  —  Lightweight core module.
Provides path helpers, logging setup, and network utilities.
"""
import os, sys, time, logging, urllib.request, urllib.error
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

# ── Network ───────────────────────────────────────────────────────────────────
def check_internet_connection(timeout=5):
    try:
        urllib.request.urlopen("https://www.google.com", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError):
        return False
