import asyncio
import webbrowser
import tkinter as tk
import keyboard
from PIL import Image

from app.config import LENS_URL, PASTE_DELAY_MS, OCR_LANGS
from app.win_api import get_primary_screen_size, copy_image_to_clipboard, copy_text_to_clipboard


class OneUIToast:
    """Ненав'язливе спливаюче сповіщення в стилі Samsung One UI."""
    def __init__(self, root: tk.Tk, text: str, duration_ms: int = 1600):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.95)
        self.win.configure(bg="#1E1E24")

        sw, sh = get_primary_screen_size()

        label = tk.Label(
            self.win,
            text=text,
            font=("Segoe UI", 10, "bold"),
            fg="#F5F5F7",
            bg="#1E1E24",
            padx=20,
            pady=10,
        )
        label.pack()

        self.win.update_idletasks()
        w = self.win.winfo_width()
        h = self.win.winfo_height()
        x = (sw - w) // 2
        y = sh - h - 64
        self.win.geometry(f"{w}x{h}+{x}+{y}")
        self.win.after(duration_ms, self.close)

    def close(self):
        try:
            self.win.destroy()
        except Exception:
            pass


def search_google_lens(root: tk.Tk, image: Image.Image):
    """Копіює вирізане зображення у буфер, відкриває Google Lens і вставляє його."""
    copy_image_to_clipboard(image)
    webbrowser.open(LENS_URL)
    root.after(PASTE_DELAY_MS, lambda: keyboard.send("ctrl+v"))


def copy_selection_image(root: tk.Tk, image: Image.Image):
    """Копіює виділений фрагмент екрана в буфер обміну."""
    copy_image_to_clipboard(image)
    OneUIToast(root, "Зображення скопійовано в буфер")


def recognize_and_copy_text(root: tk.Tk, image: Image.Image):
    """Розпізнає текст із виділеної області через Windows OCR (winocr)."""
    try:
        import winocr
        for lang in OCR_LANGS:
            try:
                coro = winocr.recognize_pil(image, lang=lang) if lang else winocr.recognize_pil(image)
                res = asyncio.run(coro)
                text = res.text.strip()
                if text:
                    copy_text_to_clipboard(text)
                    preview = text.replace("\n", " ")[:48]
                    OneUIToast(root, f"Скопійовано: «{preview}»")
                    return
            except Exception:
                continue
        OneUIToast(root, "Текст на виділенні не знайдено")
    except ImportError:
        OneUIToast(root, "Помилка: модуль winocr не встановлено")