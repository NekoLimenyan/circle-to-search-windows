import os
import sys
import io
import time
import threading
import ctypes
from ctypes import wintypes
from PIL import Image
from app.config import STATE_DIR, HOTKEY

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

# Віртуальні клавіші та константи Windows
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12
VK_ESCAPE = 0x1B
VK_Q = 0x51
VK_V = 0x56
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_LMENU = 0xA4
VK_RMENU = 0xA5
KEYEVENTF_KEYUP = 0x0002

MOD_ALT = 0x0001
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
HOTKEY_ID = 1


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
    """Перевіряє, чи живий процес служби із вказаним PID, і завершує його."""
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
            proc_name = os.path.basename(buf.value).lower()
            current_name = os.path.basename(sys.executable).lower()
            if "python" not in proc_name and proc_name != current_name:
                return False

        return bool(kernel32.TerminateProcess(h_proc, 0))
    finally:
        kernel32.CloseHandle(h_proc)


def toggle_background_service() -> str:
    """Перемикає фонову службу (ON / OFF)."""
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


def start_global_hotkey_listener(on_trigger):
    """Реєструє Alt+Q через нативний Windows RegisterHotKey (без хуків, які може вимкнути система)."""
    def _worker():
        registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT | MOD_NOREPEAT, VK_Q))
        if not registered:
            registered = bool(user32.RegisterHotKey(None, HOTKEY_ID, MOD_ALT, VK_Q))

        if registered:
            msg = wintypes.MSG()
            try:
                while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                        on_trigger()
            finally:
                user32.UnregisterHotKey(None, HOTKEY_ID)
        else:
            # Резервний варіант, якщо інший застосунок уже перехопив Alt+Q
            try:
                import keyboard
                keyboard.add_hotkey(HOTKEY, on_trigger)
                keyboard.wait()
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()


def is_escape_pressed() -> bool:
    """Миттєво перевіряє фізичний стан клавіші Esc без системного хука."""
    return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)


def get_virtual_screen_rect():
    vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
    vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
    sw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(SM_CXSCREEN)
    sh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(SM_CYSCREEN)
    return vx, vy, sw, sh


def get_primary_screen_size():
    return user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)


def get_foreground_window_info():
    """Повертає (hwnd, process_name_lower, window_title) активного вікна Windows."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 0, "", ""

    title_len = user32.GetWindowTextLengthW(hwnd)
    title_buf = ctypes.create_unicode_buffer(title_len + 1)
    user32.GetWindowTextW(hwnd, title_buf, title_len + 1)

    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    proc_name = ""
    if pid.value:
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if h_proc:
            try:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                    proc_name = os.path.basename(buf.value).lower()
            finally:
                kernel32.CloseHandle(h_proc)

    return hwnd, proc_name, title_buf.value


def send_ctrl_v():
    """Надсилає Ctrl+V на рівні Windows VK-кодів незалежно від розкладки (UA/RU/EN)."""
    for mod_vk in (VK_MENU, VK_LMENU, VK_RMENU, VK_SHIFT, VK_LWIN, VK_RWIN):
        if user32.GetAsyncKeyState(mod_vk) & 0x8000:
            scan = user32.MapVirtualKeyW(mod_vk, 0)
            user32.keybd_event(mod_vk, scan, KEYEVENTF_KEYUP, 0)

    ctrl_scan = user32.MapVirtualKeyW(VK_CONTROL, 0)
    v_scan = user32.MapVirtualKeyW(VK_V, 0)

    user32.keybd_event(VK_CONTROL, ctrl_scan, 0, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_V, v_scan, 0, 0)
    time.sleep(0.04)
    user32.keybd_event(VK_V, v_scan, KEYEVENTF_KEYUP, 0)
    time.sleep(0.02)
    user32.keybd_event(VK_CONTROL, ctrl_scan, KEYEVENTF_KEYUP, 0)


def copy_image_to_clipboard(image: Image.Image):
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, data, len(data))
    kernel32.GlobalUnlock(h_mem)

    for _ in range(8):
        if user32.OpenClipboard(0):
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_DIB, h_mem)
            user32.CloseClipboard()
            return
        time.sleep(0.015)


def copy_text_to_clipboard(text: str):
    text_bytes = (text + "\0").encode("utf-16le")
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, text_bytes, len(text_bytes))
    kernel32.GlobalUnlock(h_mem)

    for _ in range(8):
        if user32.OpenClipboard(0):
            user32.EmptyClipboard()
            user32.SetClipboardData(CF_UNICODETEXT, h_mem)
            user32.CloseClipboard()
            return
        time.sleep(0.015)