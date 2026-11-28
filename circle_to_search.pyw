import sys
import tkinter as tk

from app.config import load_last_mode, save_last_mode
from app.win_api import (
    setup_dpi_awareness,
    toggle_background_service,
    start_global_hotkey_listener,
)
from app.actions import OneUIToast
from app.overlay import OverlayUI


def main():
    setup_dpi_awareness()
    state = toggle_background_service()

    root = tk.Tk()
    root.withdraw()

    if state == "stopped":
        OneUIToast(root, "Circle to Search вимкнено", duration_ms=1300)
        root.after(1400, root.destroy)
        root.mainloop()
        sys.exit(0)

    OneUIToast(root, "Circle to Search увімкнено • Alt + Q", duration_ms=1700)

    active_overlay = None
    current_mode = load_last_mode()

    def on_overlay_finish():
        nonlocal active_overlay
        active_overlay = None

    def on_mode_change(new_mode: str):
        nonlocal current_mode
        current_mode = new_mode
        save_last_mode(new_mode)

    def trigger_overlay():
        nonlocal active_overlay
        if active_overlay is not None and not active_overlay.closed:
            try:
                if active_overlay.win.winfo_exists():
                    active_overlay.close()
                    return
            except Exception:
                pass
        active_overlay = None

        active_overlay = OverlayUI(
            root,
            on_finish=on_overlay_finish,
            initial_mode=current_mode,
            on_mode_change=on_mode_change,
        )

    start_global_hotkey_listener(lambda: root.after(0, trigger_overlay))
    root.mainloop()


if __name__ == "__main__":
    main()