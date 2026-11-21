import os
import io
import time
import tempfile
import ctypes
from ctypes import wintypes
from PIL import Image
from app.config import STATE_DIR

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

CF_DIB = 8
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

SM_CXSCREEN = 0
SM_CYSCREEN = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259
PID_FILE = os.path.join(STATE_DIR, "service.pid")


def setup_dpi_awareness():
    """Фіксує Per-Monitor DPI для чіткого рендерингу 1:1 при масштабуванні Windows."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            user32.SetProcessDPIAware()
        except Exception:
            pass


def _terminate_if_python(pid: int) -> bool:
    """Перевіряє, чи живий процес Python із вказаним PID, і завершує його."""
    if pid <= 0 or pid == os.getpid():
        return False

    h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_TERMINATE, False, pid)
    if not h_proc:
        return False

    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(h_proc, ctypes.byref(exit_code)) or exit_code.value != STILL_ACTIVE:
            return False

        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
            if "python" not in buf.value.lower():
                return False

        return bool(kernel32.TerminateProcess(h_proc, 0))
    finally:
        kernel32.CloseHandle(h_proc)


def toggle_background_service() -> str:
    """
    Перемикає фонову службу:
    - якщо вже запущена -> вимикає її та повертає 'stopped';
    - якщо вимкнена -> реєструє поточний PID та повертає 'started'.
    """
    os.makedirs(STATE_DIR, exist_ok=True)

    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                old_pid = int(f.read().strip())
            if _terminate_if_python(old_pid):
                try:
                    os.remove(PID_FILE)
                except OSError:
                    pass
                return "stopped"
        except Exception:
            pass

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(os.getpid()))
    return "started"


def get_virtual_screen_rect():
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    sw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(SM_CXSCREEN)
    sh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(SM_CYSCREEN)
    return vx, vy, sw, sh


def get_primary_screen_size():
    return user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def copy_image_to_clipboard(image: Image.Image):
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, data, len(data))
    kernel32.GlobalUnlock(h_mem)

    for _ in range(5):
        if user32.OpenClipboard(0):
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_DIB, h_mem)
            user32.CloseClipboard()
            return
        time.sleep(0.01)


def copy_text_to_clipboard(text: str):
    text_bytes = (text + "\0").encode("utf-16le")
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, text_bytes, len(text_bytes))
    kernel32.GlobalUnlock(h_mem)

    for _ in range(5):
        if user32.OpenClipboard(0):
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            user32.CloseClipboard()
            return
        time.sleep(0.01)