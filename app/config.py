import os
import json
import tempfile

HOTKEY = "alt+q"
MUTEX_NAME = "Global\\CircleToSearch_OneUI_Modular_v1"

LENS_URL = "https://lens.google.com/search?p"
PASTE_DELAY_MS = 1700
OCR_LANGS = ("uk-UA", "en-US", None)

BROWSER_PROCESSES = (
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "vivaldi.exe",
    "zen.exe",
    "arc.exe",
    "browser.exe",
)

VALID_MODES = ("rect", "lasso", "copy", "ocr")
DEFAULT_MODE = "rect"

STATE_DIR = os.path.join(os.getenv("LOCALAPPDATA") or tempfile.gettempdir(), "CircleToSearch")
STATE_FILE = os.path.join(STATE_DIR, "state.json")

# Візуальні параметри
DIM_BRIGHTNESS = 0.45
LASSO_PADDING = 14
BORDER_GLOW_WIDTH = 6
BORDER_ANIM_FRAMES = 20

# Фірмова палітра Google для переливчастої рамки
GOOGLE_STOPS = [
    (66, 133, 244),   # Blue   #4285F4
    (155, 114, 203),  # Violet #9B72CB
    (234, 67, 53),    # Red    #EA4335
    (251, 188, 5),    # Yellow #FBBC05
    (52, 168, 83),    # Green  #34A853
]


def load_last_mode() -> str:
    """Зчитує останній обраний режим із локального профілю користувача."""
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        mode = data.get("mode")
        if mode in VALID_MODES:
            return mode
    except Exception:
        pass
    return DEFAULT_MODE


def save_last_mode(mode: str):
    """Зберігає обраний режим у %LOCALAPPDATA%\\CircleToSearch\\state.json."""
    if mode not in VALID_MODES:
        return
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump({"mode": mode}, f)
    except Exception:
        pass