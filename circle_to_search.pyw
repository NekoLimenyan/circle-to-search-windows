import os
import sys
import time
import tkinter as tk

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.config import HOTKEY, load_last_mode, save_last_mode
from app.win_api import setup_dpi_awareness, toggle_background_service
from app.actions import OneUIToast
from app.overlay import OverlayUI
import keyboard


def main():
    setup_dpi_awareness()
    status = toggle_background_service()

    root = tk.Tk()
    root.withdraw()

    # Якщо служба вже працювала — вона щойно вимкнулась, показуємо Toast і виходимо
    if status == "stopped":
        OneUIToast(root, "Circle to Search вимкнено", duration_ms=1300)
        root.after(1400, root.destroy)
        root.mainloop()
        sys.exit(0)

    OneUIToast(root, "Circle to Search увімкнено • Alt + Q", duration_ms=1500)

    state = {
        "overlay": None,
        "last_toggle": 0.0,
        "mode": load_last_mode(),
    }

    def on_mode_change(new_mode: str):
        state["mode"] = new_mode
        save_last_mode(new_mode)

    def toggle_overlay():
        now = time.monotonic()
        if now - state["last_toggle"] < 0.35:
            return
        state["last_toggle"] = now

        current = state["overlay"]
        if current is not None and not current.closed:
            current.close()
            state["overlay"] = None
            return

        def on_closed():
            state["overlay"] = None

        state["overlay"] = OverlayUI(
            root,
            on_closed,
            initial_mode=state["mode"],
            on_mode_change=on_mode_change,
        )

    keyboard.add_hotkey(HOTKEY, lambda: root.after(0, toggle_overlay))
    root.mainloop()


if __name__ == "__main__":
    main()