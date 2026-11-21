import os
import sys
import time
import io
import asyncio
import webbrowser
import math
import ctypes
from ctypes import wintypes
import tkinter as tk
from PIL import ImageGrab, Image, ImageDraw, ImageEnhance, ImageTk
import keyboard

# 1. Фіксація Per-Monitor DPI для ідеальної чіткості
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

# Захист від дублювання процесів через Windows Mutex
mutex = kernel32.CreateMutexW(None, False, "Global\\CircleToSearch_OneUI_v6")
if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    sys.exit(0)

kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]

CF_DIB = 8
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002

# Метрики віртуального екрана (підтримка 1 та кількох моніторів)
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79


def copy_image_to_clipboard(image: Image.Image):
    output = io.BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, data, len(data))
    kernel32.GlobalUnlock(h_mem)
    if user32.OpenClipboard(0):
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_DIB, h_mem)
        user32.CloseClipboard()


def copy_text_to_clipboard(text: str):
    text_bytes = (text + "\0").encode("utf-16le")
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, text_bytes, len(text_bytes))
    kernel32.GlobalUnlock(h_mem)
    if user32.OpenClipboard(0):
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()


def render_rounded_pill(bg_crop: Image.Image, fill_rgba, border_rgba, radius: int) -> Image.Image:
    """Рендерить ідеально згладжену капсулу поверх фрагмента фону (2x supersampling)."""
    w, h = bg_crop.size
    scale = 2
    hi = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(hi)
    draw.rounded_rectangle(
        [1, 1, w * scale - 2, h * scale - 2],
        radius=radius * scale,
        fill=fill_rgba,
        outline=border_rgba,
        width=scale,
    )
    pill = hi.resize((w, h), Image.Resampling.LANCZOS)
    return Image.alpha_composite(bg_crop.convert("RGBA"), pill).convert("RGB")


class OneUIToast:
    """Ненав'язливе спливаюче сповіщення в стилі Samsung One UI без звуку помилки."""
    def __init__(self, root: tk.Tk, text: str, duration_ms: int = 1600):
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.configure(bg="#1E1E22")

        sw = user32.GetSystemMetrics(0)
        sh = user32.GetSystemMetrics(1)

        label = tk.Label(
            self.win,
            text=text,
            font=("Segoe UI", 10, "bold"),
            fg="#F5F5F7",
            bg="#1E1E22",
            padx=18,
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


class OverlayUI:
    def __init__(self, master: tk.Tk, on_finish):
        self.master = master
        self.on_finish = on_finish
        self.closed = False

        # Координати віртуального робочого столу
        self.vx = user32.GetSystemMetrics(SM_XVIRTUALSCREEN)
        self.vy = user32.GetSystemMetrics(SM_YVIRTUALSCREEN)
        self.sw = user32.GetSystemMetrics(SM_CXVIRTUALSCREEN) or user32.GetSystemMetrics(0)
        self.sh = user32.GetSystemMetrics(SM_CYVIRTUALSCREEN) or user32.GetSystemMetrics(1)

        # Миттєве захоплення екрана та створення затемненої підкладки
        try:
            self.screenshot = ImageGrab.grab(all_screens=True)
        except Exception:
            self.screenshot = ImageGrab.grab()

        self.dimmed = ImageEnhance.Brightness(self.screenshot).enhance(0.45)

        self.win = tk.Toplevel(master)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.geometry(f"{self.sw}x{self.sh}+{self.vx}+{self.vy}")

        self.canvas = tk.Canvas(
            self.win,
            width=self.sw,
            height=self.sh,
            bg="#000000",
            cursor="crosshair",
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        # Базове затемнене зображення екрана
        self.bg_photo = ImageTk.PhotoImage(self.dimmed)
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        # Елементи динамічного виділення (Spotlight)
        self.sel_photo = None
        self.sel_img_id = self.canvas.create_image(0, 0, anchor="nw")
        self.lasso_line_id = None
        self.bracket_ids = []

        self.mode = "rect"  # rect | lasso | copy | ocr
        self.start_x = None
        self.start_y = None
        self.lasso_points = []
        self.last_crop_box = None

        # Позиціонування тулбару по центру основного монітора
        primary_w = user32.GetSystemMetrics(0)
        offset_x = abs(self.vx) if self.vx < 0 else 0
        self.tb_w = 220
        self.tb_h = 44
        self.tb_x = offset_x + (primary_w - self.tb_w) // 2
        self.tb_y = 22
        self.btn_w = self.tb_w // 5
        self.active_slider_x = float(self.tb_x)

        self.buttons = [
            {"id": "rect", "cx": self.tb_x},
            {"id": "lasso", "cx": self.tb_x + self.btn_w},
            {"id": "copy", "cx": self.tb_x + self.btn_w * 2},
            {"id": "ocr", "cx": self.tb_x + self.btn_w * 3},
            {"id": "close", "cx": self.tb_x + self.btn_w * 4},
        ]
        self.icon_shapes = []
        self.glow_phase = 0.0
        self.slider_animating = False

        self.setup_ui()
        self.animate_aura()

        # Події миші та клавіатури
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<ButtonPress-3>", self.cancel)
        self.win.bind("<Escape>", self.cancel)
        self.win.bind("<Control-c>", self.quick_copy_current)
        self.win.bind("<Control-C>", self.quick_copy_current)

        self.win.focus_force()
        self.win.grab_set()

    def draw_gradient_line(self, x1, y1, x2, y2, c1, c2, steps=28):
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        dx, dy = (x2 - x1) / steps, (y2 - y1) / steps
        for i in range(steps):
            cx1, cy1 = x1 + dx * i, y1 + dy * i
            cx2, cy2 = x1 + dx * (i + 1), y1 + dy * (i + 1)
            t = i / steps
            color = f"#{int(r1 + (r2 - r1) * t):02x}{int(g1 + (g2 - g1) * t):02x}{int(b1 + (b2 - b1) * t):02x}"
            self.canvas.create_line(
                cx1, cy1, cx2, cy2, fill=color, width=3, tags="glow", capstyle=tk.ROUND
            )

    def round_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def draw_vector_icon(self, btn_id, cx, cy, color):
        shapes = []
        if btn_id == "rect":
            # Рамка пошуку
            shapes.append(
                self.round_rect(cx - 7, cy - 7, cx + 7, cy + 7, 3, outline=color, width=1.8, fill="")
            )
        elif btn_id == "lasso":
            # Хвилясте ласо (Circle to Search)
            shapes.append(
                self.canvas.create_line(
                    cx - 8, cy + 3, cx - 3, cy - 5, cx + 3, cy + 5, cx + 8, cy - 3,
                    smooth=True, fill=color, width=2.0, capstyle=tk.ROUND,
                )
            )
        elif btn_id == "copy":
            # Два перекриті квадрати (Копіювати в буфер)
            shapes.append(
                self.canvas.create_rectangle(cx - 6, cy - 4, cx + 2, cy + 6, outline=color, width=1.7)
            )
            shapes.append(
                self.canvas.create_line(
                    cx - 2, cy - 6, cx + 6, cy - 6, cx + 6, cy + 3,
                    fill=color, width=1.7, capstyle=tk.ROUND,
                )
            )
        elif btn_id == "ocr":
            # Літера T (Розпізнавання тексту)
            shapes.append(
                self.canvas.create_line(cx - 6, cy - 6, cx + 6, cy - 6, fill=color, width=2.0, capstyle=tk.ROUND)
            )
            shapes.append(
                self.canvas.create_line(cx, cy - 6, cx, cy + 7, fill=color, width=2.0, capstyle=tk.ROUND)
            )
        elif btn_id == "close":
            shapes.append(
                self.canvas.create_line(cx - 5, cy - 5, cx + 5, cy + 5, fill="#FF6B6B", width=2.0, capstyle=tk.ROUND)
            )
            shapes.append(
                self.canvas.create_line(cx + 5, cy - 5, cx - 5, cy + 5, fill="#FF6B6B", width=2.0, capstyle=tk.ROUND)
            )
        return shapes

    def setup_ui(self):
        # 1. Градієнтна рамка Google по периметру екрана
        w = 2
        self.draw_gradient_line(w, w, self.sw - w, w, "#4285F4", "#EA4335")
        self.draw_gradient_line(self.sw - w, w, self.sw - w, self.sh - w, "#EA4335", "#FBBC05")
        self.draw_gradient_line(self.sw - w, self.sh - w, w, self.sh - w, "#FBBC05", "#34A853")
        self.draw_gradient_line(w, self.sh - w, w, w, "#34A853", "#4285F4")

        # 2. Ідеально згладжена One UI капсула тулбару
        bg_slice = self.dimmed.crop((self.tb_x, self.tb_y, self.tb_x + self.tb_w, self.tb_y + self.tb_h))
        pill_img = render_rounded_pill(
            bg_slice,
            fill_rgba=(28, 28, 32, 238),
            border_rgba=(68, 68, 76, 255),
            radius=self.tb_h // 2,
        )
        self.tb_photo = ImageTk.PhotoImage(pill_img)
        self.tb_bg_id = self.canvas.create_image(self.tb_x, self.tb_y, anchor="nw", image=self.tb_photo, tags="ui")

        # 3. Активний індикатор-слайдер
        pad = 5
        self.slider = self.round_rect(
            self.active_slider_x + pad,
            self.tb_y + pad,
            self.active_slider_x + self.btn_w - pad,
            self.tb_y + self.tb_h - pad,
            16,
            fill="#3B3B42",
            outline="",
            tags="ui",
        )

        # 4. Векторні іконки
        self.update_icon_colors()

    def set_mode(self, mode_id):
        if mode_id == "close":
            self.cancel()
            return
        self.mode = mode_id
        self.update_icon_colors()
        if not self.slider_animating:
            self.slider_animating = True
            self.animate_slider()

    def update_icon_colors(self):
        for shape_id in self.icon_shapes:
            self.canvas.delete(shape_id)
        self.icon_shapes.clear()

        for btn in self.buttons:
            cx = btn["cx"] + self.btn_w // 2
            cy = self.tb_y + self.tb_h // 2
            color = "#FFFFFF" if btn["id"] == self.mode else "#8E8E95"
            for item in self.draw_vector_icon(btn["id"], cx, cy, color):
                self.canvas.addtag_withtag("ui", item)
                self.icon_shapes.append(item)

    def animate_slider(self):
        if self.closed:
            return
        target_x = next(b["cx"] for b in self.buttons if b["id"] == self.mode)
        diff = target_x - self.active_slider_x

        if abs(diff) < 0.4:
            self.active_slider_x = float(target_x)
            self.slider_animating = False
        else:
            self.active_slider_x += diff * 0.3

        pad = 5
        self.canvas.delete(self.slider)
        self.slider = self.round_rect(
            self.active_slider_x + pad,
            self.tb_y + pad,
            self.active_slider_x + self.btn_w - pad,
            self.tb_y + self.tb_h - pad,
            16,
            fill="#3B3B42",
            outline="",
            tags="ui",
        )
        self.canvas.tag_raise(self.tb_bg_id)
        self.canvas.tag_raise(self.slider)
        for shape_id in self.icon_shapes:
            self.canvas.tag_raise(shape_id)

        if self.slider_animating:
            self.win.after(16, self.animate_slider)

    def animate_aura(self):
        if self.closed:
            return
        self.glow_phase += 0.1
        width_var = 3.2 + math.sin(self.glow_phase) * 1.3
        for item in self.canvas.find_withtag("glow"):
            self.canvas.itemconfig(item, width=width_var)
        self.win.after(32, self.animate_aura)

    def draw_selection_brackets(self, x1, y1, x2, y2):
        """Малює акуратні кутові маркери та тонку рамку навколо світлої зони."""
        for bid in self.bracket_ids:
            self.canvas.delete(bid)
        self.bracket_ids.clear()

        # Тонка напівпрозора рамка
        rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="#D0D7DE", width=1)
        self.bracket_ids.append(rect)

        # Кутові акценти в стилі One UI
        blen = min(16, (x2 - x1) // 3, (y2 - y1) // 3)
        if blen >= 5:
            c = "#FFFFFF"
            w = 3
            corners = [
                (x1, y1 + blen, x1, y1, x1 + blen, y1),
                (x2 - blen, y1, x2, y1, x2, y1 + blen),
                (x2, y2 - blen, x2, y2, x2 - blen, y2),
                (x1 + blen, y2, x1, y2, x1, y2 - blen),
            ]
            for pts in corners:
                line = self.canvas.create_line(*pts, fill=c, width=w, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                self.bracket_ids.append(line)

        self.canvas.tag_raise("ui")

    def on_press(self, event):
        # Клік по панелі інструментів
        if self.tb_y <= event.y <= self.tb_y + self.tb_h and self.tb_x <= event.x <= self.tb_x + self.tb_w:
            btn_idx = (event.x - self.tb_x) // self.btn_w
            if 0 <= btn_idx < len(self.buttons):
                self.set_mode(self.buttons[btn_idx]["id"])
            return

        self.start_x = event.x
        self.start_y = event.y
        self.last_crop_box = None

        if self.lasso_line_id:
            self.canvas.delete(self.lasso_line_id)
            self.lasso_line_id = None

        if self.mode == "lasso":
            self.lasso_points = [(event.x, event.y)]
            self.lasso_line_id = self.canvas.create_line(
                event.x, event.y, event.x, event.y,
                fill="#8AB4F8", width=4, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True
            )

    def on_drag(self, event):
        if self.start_x is None:
            return

        if self.mode in ("rect", "copy", "ocr"):
            x1 = max(0, min(self.start_x, event.x))
            y1 = max(0, min(self.start_y, event.y))
            x2 = min(self.sw, max(self.start_x, event.x))
            y2 = min(self.sh, max(self.start_y, event.y))

            if (x2 - x1) > 4 and (y2 - y1) > 4:
                self.last_crop_box = (x1, y1, x2, y2)
                crop = self.screenshot.crop(self.last_crop_box)
                self.sel_photo = ImageTk.PhotoImage(crop)
                self.canvas.coords(self.sel_img_id, x1, y1)
                self.canvas.itemconfig(self.sel_img_id, image=self.sel_photo)
                self.draw_selection_brackets(x1, y1, x2, y2)

        elif self.mode == "lasso":
            self.lasso_points.append((event.x, event.y))
            if len(self.lasso_points) >= 2 and self.lasso_line_id:
                flat_coords = [coord for pt in self.lasso_points for coord in pt]
                self.canvas.coords(self.lasso_line_id, *flat_coords)
                self.canvas.tag_raise("ui")

    def build_result_image(self, event=None):
        if self.mode in ("rect", "copy", "ocr") and self.start_x is not None:
            ex = event.x if event else (self.last_crop_box[2] if self.last_crop_box else self.start_x)
            ey = event.y if event else (self.last_crop_box[3] if self.last_crop_box else self.start_y)
            x1 = max(0, min(self.start_x, ex))
            y1 = max(0, min(self.start_y, ey))
            x2 = min(self.sw, max(self.start_x, ex))
            y2 = min(self.sh, max(self.start_y, ey))
            if (x2 - x1) > 12 and (y2 - y1) > 12:
                return self.screenshot.crop((x1, y1, x2, y2)), (x1, y1, x2, y2)

        elif self.mode == "lasso" and len(self.lasso_points) > 2:
            xs = [p[0] for p in self.lasso_points]
            ys = [p[1] for p in self.lasso_points]
            x1, y1 = max(0, min(xs)), max(0, min(ys))
            x2, y2 = min(self.sw, max(xs)), min(self.sh, max(ys))
            if (x2 - x1) > 12 and (y2 - y1) > 12:
                bbox_img = self.screenshot.crop((x1, y1, x2, y2))
                mask = Image.new("L", bbox_img.size, 0)
                draw = ImageDraw.Draw(mask)
                shifted = [(p[0] - x1, p[1] - y1) for p in self.lasso_points]
                draw.polygon(shifted, fill=255)

                final_img = Image.new("RGB", bbox_img.size, (255, 255, 255))
                final_img.paste(bbox_img, (0, 0), mask)
                return final_img, (x1, y1, x2, y2)

        return None, None

    def quick_copy_current(self, event=None):
        img, _ = self.build_result_image()
        if img:
            copy_image_to_clipboard(img)
            self.cancel()
            OneUIToast(self.master, "Зображення скопійовано в буфер")

    def on_release(self, event):
        if self.start_x is None:
            return

        result_img, box = self.build_result_image(event)
        current_mode = self.mode

        if result_img and current_mode == "lasso" and box:
            # Короткий візуальний фідбек виділеного контуру перед закриттям
            self.sel_photo = ImageTk.PhotoImage(result_img)
            self.canvas.coords(self.sel_img_id, box[0], box[1])
            self.canvas.itemconfig(self.sel_img_id, image=self.sel_photo)
            self.win.update()
            time.sleep(0.09)

        self.cancel()

        if result_img:
            if current_mode in ("rect", "lasso"):
                self.run_lens_search(result_img)
            elif current_mode == "copy":
                copy_image_to_clipboard(result_img)
                OneUIToast(self.master, "Скріншот скопійовано в буфер")
            elif current_mode == "ocr":
                self.run_ocr(result_img)

    def run_lens_search(self, image: Image.Image):
        copy_image_to_clipboard(image)
        webbrowser.open("https://lens.google.com/search?p")
        # Вставка через 1.7 с (якщо сторінка завантажилась повільніше — картинка вже в буфері для Ctrl+V)
        self.master.after(1700, lambda: keyboard.send("ctrl+v"))

    def run_ocr(self, image: Image.Image):
        try:
            import winocr
            for lang in ("uk-UA", "en-US", None):
                try:
                    res = asyncio.run(
                        winocr.recognize_pil(image, lang=lang) if lang else winocr.recognize_pil(image)
                    )
                    text = res.text.strip()
                    if text:
                        copy_text_to_clipboard(text)
                        preview = text.replace("\n", " ")[:48]
                        OneUIToast(self.master, f"Скопійовано: «{preview}»")
                        return
                except Exception:
                    continue
            OneUIToast(self.master, "Текст на виділенні не знайдено")
        except ImportError:
            OneUIToast(self.master, "Помилка: модуль winocr не встановлено")

    def cancel(self, event=None):
        if self.closed:
            return
        self.closed = True
        try:
            self.win.grab_release()
            self.win.destroy()
        except Exception:
            pass
        self.on_finish()


def main():
    root = tk.Tk()
    root.withdraw()  # Головний потік залишається живим у фоні

    active_overlay = {"instance": None}

    def toggle_overlay():
        if active_overlay["instance"] and not active_overlay["instance"].closed:
            active_overlay["instance"].cancel()
            active_overlay["instance"] = None
            return

        def on_done():
            active_overlay["instance"] = None

        active_overlay["instance"] = OverlayUI(root, on_done)

    # Повторне натискання Alt+Q тепер плавно закриває оверлей
    keyboard.add_hotkey("alt+q", lambda: root.after(0, toggle_overlay))
    root.mainloop()


if __name__ == "__main__":
    main()