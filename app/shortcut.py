import os
import sys
import subprocess
from app.icon_gen import generate_lens_icon


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
    app_dir = os.path.dirname(os.path.abspath(__file__))
    project_dir = os.path.dirname(app_dir)
    target_pyw = os.path.join(project_dir, "circle_to_search.pyw")
    icon_path = generate_lens_icon(os.path.join(app_dir, "circle_to_search.ico"))
    pythonw = find_pythonw()

    # 1. Робочий стіл
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    if os.path.isdir(desktop):
        _create_windows_lnk(
            os.path.join(desktop, "Circle to Search.lnk"),
            pythonw,
            f'"{target_pyw}"',
            project_dir,
            icon_path,
        )

    # 2. Меню «Пуск» (зручно шукати через Win або закріпити на панелі завдань)
    start_menu = os.path.join(
        os.getenv("APPDATA", ""),
        "Microsoft",
        "Windows",
        "Start Menu",
        "Programs",
    )
    if os.path.isdir(start_menu):
        _create_windows_lnk(
            os.path.join(start_menu, "Circle to Search.lnk"),
            pythonw,
            f'"{target_pyw}"',
            project_dir,
            icon_path,
        )

    # 3. Автозавантаження Windows (за запитом)
    if add_startup:
        startup_dir = os.path.join(
            os.getenv("APPDATA", ""),
            "Microsoft",
            "Windows",
            "Start Menu",
            "Programs",
            "Startup",
        )
        if os.path.isdir(startup_dir):
            _create_windows_lnk(
                os.path.join(startup_dir, "Circle to Search.lnk"),
                pythonw,
                f'"{target_pyw}"',
                project_dir,
                icon_path,
            )


if __name__ == "__main__":
    install_shortcuts(add_startup="--startup" in sys.argv)
    print("Ярлики та іконку успішно створено.")