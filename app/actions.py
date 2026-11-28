import time
import ctypes
import asyncio
import threading
import webbrowser
import tkinter as tk
from PIL import Image

from app.config import LENS_URL, OCR_LANGS, BROWSER_PROCESSES
from app.win_api import (
    get_primary_screen_size,
    get_foreground_window_info,
    send_ctrl_v,
    copy_image_to_clipboard,
    copy_text_to_clipboard,
)
from app.graphics import prepare_image_for_ocr

ALLOWED_PUNCT = set(" .,!?:;-—–()[]{}'\"/\\@#$%&*+=<>_~`№|«»")


class OneUIToast:
    """Ненав'язливе спливаюче сповіщення в стилі Samsung One UI."""
    def __init__(self, root: tk.Tk, text: str, duration_ms: int = 1800):
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
    """Відкриває Google Lens, чекає фокуса браузера та гарантовано вставляє скріншот."""
    copy_image_to_clipboard(image)
    webbrowser.open(LENS_URL)

    def _paste_worker():
        deadline = time.monotonic() + 5.0
        browser_ready = False
        while time.monotonic() < deadline:
            _, proc_name, _ = get_foreground_window_info()
            if proc_name in BROWSER_PROCESSES:
                browser_ready = True
                break
            time.sleep(0.1)

        time.sleep(1.05 if browser_ready else 1.8)
        copy_image_to_clipboard(image)

        _, proc_name, title_before = get_foreground_window_info()
        if proc_name in BROWSER_PROCESSES or not browser_ready:
            send_ctrl_v()

            time.sleep(1.25)
            _, proc_after, title_after = get_foreground_window_info()
            if proc_after in BROWSER_PROCESSES and title_after == title_before:
                send_ctrl_v()

    threading.Thread(target=_paste_worker, daemon=True).start()


def copy_selection_image(root: tk.Tk, image: Image.Image):
    """Копіює виділений фрагмент екрана в буфер обміну."""
    copy_image_to_clipboard(image)
    OneUIToast(root, "Зображення скопійовано в буфер")


def _clean_ocr_text(raw: str) -> str:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    return "\n".join(lines).strip()


def _score_ocr_text(text: str) -> float:
    """Оцінює якість розпізнаного тексту; повертає -1, якщо це випадковий набір символів."""
    if not text:
        return -1.0

    non_space = [ch for ch in text if not ch.isspace()]
    if not non_space:
        return -1.0

    alnum_count = sum(1 for ch in non_space if ch.isalnum())
    weird_count = sum(1 for ch in non_space if not ch.isalnum() and ch not in ALLOWED_PUNCT)

    if alnum_count == 0:
        return -1.0
    if alnum_count < 2 and len(non_space) > 2:
        return -1.0
    if weird_count / len(non_space) > 0.30:
        return -1.0

    alnum_ratio = alnum_count / len(non_space)
    return alnum_count * alnum_ratio - weird_count * 3.0


def _detect_system_ocr_langs():
    """Повертає список доступних мов Windows OCR на поточному ПК."""
    try:
        from winrt.windows.media.ocr import OcrEngine
        installed = [lang.language_tag for lang in OcrEngine.available_recognizer_languages]
        if not installed:
            return []

        ordered = []
        for pref in ("uk-UA", "ru-RU", "en-US"):
            for tag in installed:
                if tag.lower() == pref.lower() and tag not in ordered:
                    ordered.append(tag)
        for tag in installed:
            if tag not in ordered:
                ordered.append(tag)
        ordered.append(None)
        return ordered
    except Exception:
        return list(OCR_LANGS)


def recognize_and_copy_text(root: tk.Tk, image: Image.Image):
    """Розпізнає текст із попередньою обробкою зображення та автовизначенням мов Windows."""
    def _ocr_worker():
        try:
            ctypes.windll.ole32.CoInitializeEx(0, 0)
        except Exception:
            pass

        try:
            import winocr
        except Exception as e:
            root.after(0, lambda: OneUIToast(root, f"Помилка модуля OCR: {type(e).__name__}"))
            return

        langs_to_try = _detect_system_ocr_langs()
        if langs_to_try == []:
            root.after(
                0,
                lambda: OneUIToast(root, "У Windows не встановлено мовні пакети OCR", duration_ms=2600),
            )
            return

        candidates = [
            prepare_image_for_ocr(image, high_contrast=False),
            prepare_image_for_ocr(image, high_contrast=True),
        ]

        best_text = ""
        best_score = -1.0
        succeeded_any = False
        last_error = ""

        for idx, prep_img in enumerate(candidates):
            for lang in langs_to_try:
                try:
                    coro = winocr.recognize_pil(prep_img, lang=lang) if lang else winocr.recognize_pil(prep_img)
                    res = asyncio.run(coro)
                    succeeded_any = True
                    cleaned = _clean_ocr_text(res.text)
                    score = _score_ocr_text(cleaned)
                    if score > best_score:
                        best_score = score
                        best_text = cleaned
                except Exception as e:
                    last_error = str(e) or type(e).__name__
                    continue

            if idx == 0 and best_score >= 6.0:
                break

        if best_text and best_score > 0:
            copy_text_to_clipboard(best_text)
            preview = best_text.replace("\n", " ")[:48]
            root.after(0, lambda: OneUIToast(root, f"Скопійовано: «{preview}»"))
        elif not succeeded_any and last_error:
            root.after(0, lambda: OneUIToast(root, f"Помилка Windows OCR: {last_error[:42]}", duration_ms=2600))
        else:
            root.after(0, lambda: OneUIToast(root, "Текст не розпізнано"))

    threading.Thread(target=_ocr_worker, daemon=True).start()