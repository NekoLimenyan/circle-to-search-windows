import os
import sys
import ctypes
import subprocess
from app.icon_gen import generate_lens_icon

# Системні константи Windows Shell (враховують перенесення папок у OneDrive)
CSIDL_PROGRAMS = 0x0002
CSIDL_STARTUP = 0x0007
CSIDL_DESKTOPDIRECTORY = 0x0010


def _get_shell_folder(csidl: int) -> str:
    buf = ctypes.create_unicode_buffer(260)
    if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
        return buf.value
    return ""


def find_pythonw() -> str:
    """Знаходить шлях до pythonw.exe поруч із поточним інтерпретатором."""
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    candidate = os.path.join(exe_dir, "pythonw.exe")
    return candidate if os.path.exists(candidate) else "pythonw.exe"


def _create_windows_lnk(lnk_path: str, target: str, args: str, work_dir: str, icon_path: str):
    env = os.environ.copy()
    env["CTS_LNK"] = lnk_path
    env["CTS_TARGET"] = target
    env["CTS_ARGS"] = args
    env["CTS_DIR"] = work_dir
    env["CTS_ICON"] = icon_path

    ps_script = (
        "$ws = New-Object -ComObject WScript.Shell; "
        "$sc = $ws.CreateShortcut($env:CTS_LNK); "
        "$sc.TargetPath = $env:CTS_TARGET; "
        "$sc.Arguments = $env:CTS_ARGS; "
        "$sc.WorkingDirectory = $env:CTS_DIR; "
        "$sc.IconLocation = $env:CTS_ICON; "
        "$sc.Description = 'Circle to Search (Увімкнути / Вимкнути)'; "
        "$sc.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
        env=env,
        check=True,
    )


def install_shortcuts(add_startup: bool = False):
    if getattr(sys, "frozen", False):
        target = os.path.abspath(sys.executable)
        args = ""
        work_dir = os.path.dirname(target)
        icon_path = target
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        project_dir = os.path.dirname(app_dir)
        target_pyw = os.path.join(project_dir, "circle_to_search.pyw")
        icon_path = generate_lens_icon(os.path.join(app_dir, "circle_to_search.ico"))
        target = find_pythonw()
        args = f'"{target_pyw}"'
        work_dir = project_dir

    # 1. Робочий стіл
    desktop = _get_shell_folder(CSIDL_DESKTOPDIRECTORY)
    if desktop and os.path.isdir(desktop):
        _create_windows_lnk(
            os.path.join(desktop, "Circle to Search.lnk"),
            target,
            args,
            work_dir,
            icon_path,
        )

    # 2. Меню «Пуск»
    start_menu = _get_shell_folder(CSIDL_PROGRAMS)
    if start_menu and os.path.isdir(start_menu):
        _create_windows_lnk(
            os.path.join(start_menu, "Circle to Search.lnk"),
            target,
            args,
            work_dir,
            icon_path,
        )

    # 3. Автозавантаження Windows (за запитом)
    if add_startup:
        startup_dir = _get_shell_folder(CSIDL_STARTUP)
        if startup_dir and os.path.isdir(startup_dir):
            _create_windows_lnk(
                os.path.join(startup_dir, "Circle to Search.lnk"),
                target,
                args,
                work_dir,
                icon_path,
            )