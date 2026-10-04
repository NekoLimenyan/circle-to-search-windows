import os
import sys
import time
import tempfile
import io
import asyncio
import webbrowser
import math
import tkinter as tk
from PIL import ImageGrab, Image, ImageDraw
import keyboard
import ctypes
from ctypes import wintypes

# Фіксація DPI для ідеальної чіткості
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

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
PROCESS_TERMINATE = 0x0001
PID_FILE = os.path.join(tempfile.gettempdir(), "circle_to_search_v5.pid")

def show_box(title, message):
    user32.MessageBoxW(0, message, title, 0x00000040 | 0x00040000)

def kill_process(pid):
    handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
    if handle:
        kernel32.TerminateProcess(handle, 0)
        kernel32.CloseHandle(handle)
        return True
    return False

if os.path.exists(PID_FILE):
    try:
        with open(PID_FILE, "r") as f:
            old_pid = int(f.read().strip())
        if kill_process(old_pid):
            if os.path.exists(PID_FILE):
                os.remove(PID_FILE)
            sys.exit(0)
    except Exception:
        pass

with open(PID_FILE, "w") as f:
    f.write(str(os.getpid()))

def copy_image_to_clipboard(image):
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

def copy_text_to_clipboard(text):
    text_bytes = (text + "\0").encode("utf-16le")
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(text_bytes))
    mem_ptr = kernel32.GlobalLock(h_mem)
    ctypes.memmove(mem_ptr, text_bytes, len(text_bytes))
    kernel32.GlobalUnlock(h_mem)
    if user32.OpenClipboard(0):
        user32.EmptyClipboard()
        user32.SetClipboardData(CF_UNICODETEXT, h_mem)
        user32.CloseClipboard()

def search_lens(image):
    copy_image_to_clipboard(image)
    webbrowser.open("https://lens.google.com/search?p")
    time.sleep(1.8)
    keyboard.send("ctrl+v")

def process_ocr(image):
    try:
        import winocr
        try:
            res = asyncio.run(winocr.recognize_pil(image, lang="uk-UA"))
        except Exception:
            try:
                res = asyncio.run(winocr.recognize_pil(image, lang="ru-RU"))
            except Exception:
                res = asyncio.run(winocr.recognize_pil(image))
                
        text = res.text.strip()
        if text:
            copy_text_to_clipboard(text)
            show_box("Текст скопійовано!", f"Розпізнано:\n\n{text[:100]}")
        else:
            show_box("OCR", "Текст не знайдено.")
    except Exception as e:
        show_box("Помилка OCR", "Бібліотеку winocr не знайдено.")

class OverlayUI:
    def __init__(self):
        self.screenshot = ImageGrab.grab()
        self.sw = self.screenshot.width
        self.sh = self.screenshot.height

        self.root = tk.Tk()
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.0)

        # Темний фон (matte)
        self.canvas = tk.Canvas(self.root, bg="#000000", cursor="cross", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        self.mode = "rect"
        self.start_x = None
        self.start_y = None
        self.rect_id = None
        self.lasso_points = []
        self.result_img = None

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<Escape>", self.cancel)
        self.canvas.bind("<Escape>", self.cancel)

        # Компактні розміри тулбару (мінімалізм)
        self.tb_w = 160
        self.tb_h = 36
        self.tb_x = (self.sw - self.tb_w) // 2
        self.tb_y = 20
        self.btn_w = self.tb_w // 4
        self.active_slider_x = self.tb_x
        
        self.buttons = [
            {"id": "rect", "cx": self.tb_x},
            {"id": "lasso", "cx": self.tb_x + self.btn_w},
            {"id": "ocr", "cx": self.tb_x + self.btn_w * 2},
            {"id": "close", "cx": self.tb_x + self.btn_w * 3}
        ]
        self.icon_shapes = []
        self.glow_phase = 0.0

        self.setup_ui()
        self.animate_in(0.0)
        self.animate_aura()
        self.animate_slider()

        self.root.focus_force()
        self.root.mainloop()

        if self.result_img:
            if self.mode in ("rect", "lasso"):
                search_lens(self.result_img)
            elif self.mode == "ocr":
                process_ocr(self.result_img)

    def draw_gradient_line(self, x1, y1, x2, y2, c1, c2, steps=30):
        """Отрисовывает плавный градиент для контуров экрана"""
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        dx, dy = (x2 - x1) / steps, (y2 - y1) / steps
        for i in range(steps):
            cx1, cy1 = x1 + dx * i, y1 + dy * i
            cx2, cy2 = x1 + dx * (i + 1), y1 + dy * (i + 1)
            r = int(r1 + (r2 - r1) * (i / steps))
            g = int(g1 + (g2 - g1) * (i / steps))
            b = int(b1 + (b2 - b1) * (i / steps))
            color = f"#{r:02x}{g:02x}{b:02x}"
            self.canvas.create_line(cx1, cy1, cx2, cy2, fill=color, width=4, tags="glow", capstyle=tk.ROUND)

    def round_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
                  x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
                  x1, y2, x1, y2-radius, x1, y1+radius, x1, y1]
        return self.canvas.create_polygon(points, smooth=True, **kwargs)

    def draw_vector_icon(self, btn_id, cx, cy, color):
        """Кастомні векторні іконки замість шрифтів"""
        shapes = []
        if btn_id == "rect":
            shapes.append(self.round_rect(cx-6, cy-6, cx+6, cy+6, 3, outline=color, width=1.5, fill=""))
        elif btn_id == "lasso":
            # Хвиляста лінія для ласо
            shapes.append(self.canvas.create_line(cx-7, cy+3, cx-3, cy-4, cx+3, cy+4, cx+7, cy-3, smooth=True, fill=color, width=1.8))
        elif btn_id == "ocr":
            shapes.append(self.canvas.create_line(cx-5, cy-5, cx+5, cy-5, fill=color, width=1.8, capstyle=tk.ROUND))
            shapes.append(self.canvas.create_line(cx, cy-5, cx, cy+6, fill=color, width=1.8, capstyle=tk.ROUND))
        elif btn_id == "close":
            shapes.append(self.canvas.create_line(cx-4, cy-4, cx+4, cy+4, fill="#ff5c5c", width=1.8, capstyle=tk.ROUND))
            shapes.append(self.canvas.create_line(cx+4, cy-4, cx-4, cy+4, fill="#ff5c5c", width=1.8, capstyle=tk.ROUND))
        return shapes

    def setup_ui(self):
        # 1. Градієнтна рамка
        w = 2
        self.draw_gradient_line(w, w, self.sw-w, w, "#4285F4", "#EA4335") # Верх
        self.draw_gradient_line(self.sw-w, w, self.sw-w, self.sh-w, "#EA4335", "#FBBC05") # Право
        self.draw_gradient_line(self.sw-w, self.sh-w, w, self.sh-w, "#FBBC05", "#34A853") # Низ
        self.draw_gradient_line(w, self.sh-w, w, w, "#34A853", "#4285F4") # Ліво

        # 2. Основа тулбару
        self.round_rect(self.tb_x, self.tb_y, self.tb_x + self.tb_w, self.tb_y + self.tb_h, 18, fill="#252528", outline="#303033", width=1)
        
        # 3. Слайдер
        pad = 4
        self.slider = self.round_rect(self.active_slider_x + pad, self.tb_y + pad, 
                                      self.active_slider_x + self.btn_w - pad, self.tb_y + self.tb_h - pad, 
                                      14, fill="#404044", outline="")

        # 4. Отрисовка векторних іконок
        for btn in self.buttons:
            cx = btn["cx"] + self.btn_w // 2
            cy = self.tb_y + self.tb_h // 2
            self.icon_shapes.extend(self.draw_vector_icon(btn["id"], cx, cy, "#858589"))

        self.update_icon_colors()

    def set_mode(self, mode_id):
        if mode_id == "close":
            self.cancel()
            return
        self.mode = mode_id
        self.update_icon_colors()

    def update_icon_colors(self):
        # Очищуємо старі іконки і малюємо нові з правильним кольором
        for shape_id in self.icon_shapes:
            self.canvas.delete(shape_id)
        self.icon_shapes.clear()

        for btn in self.buttons:
            cx = btn["cx"] + self.btn_w // 2
            cy = self.tb_y + self.tb_h // 2
            color = "#FFFFFF" if btn["id"] == self.mode else "#858589"
            self.icon_shapes.extend(self.draw_vector_icon(btn["id"], cx, cy, color))

    # --- Анімації ---
    def animate_in(self, alpha):
        if alpha < 0.55:
            alpha += 0.05
            self.root.attributes("-alpha", alpha)
            self.root.after(16, self.animate_in, alpha)

    def animate_slider(self):
        target_x = next(b["cx"] for b in self.buttons if b["id"] == self.mode)
        diff = target_x - self.active_slider_x
        self.active_slider_x += diff * 0.25 

        pad = 4
        self.canvas.delete(self.slider)
        self.slider = self.round_rect(self.active_slider_x + pad, self.tb_y + pad, 
                                      self.active_slider_x + self.btn_w - pad, self.tb_y + self.tb_h - pad, 
                                      14, fill="#404044", outline="")
        self.canvas.tag_lower(self.slider)
        
        for shape_id in self.icon_shapes:
            self.canvas.tag_raise(shape_id)

        self.root.after(16, self.animate_slider)

    def animate_aura(self):
        # Легка пульсація рамки
        self.glow_phase += 0.1
        width_var = 4 + math.sin(self.glow_phase) * 1.5
        for item in self.canvas.find_withtag("glow"):
            self.canvas.itemconfig(item, width=width_var)
        self.root.after(30, self.animate_aura)

    # --- Обробка миші ---
    def on_press(self, event):
        if self.tb_y <= event.y <= self.tb_y + self.tb_h and self.tb_x <= event.x <= self.tb_x + self.tb_w:
            rel_x = event.x - self.tb_x
            btn_idx = rel_x // self.btn_w
            if 0 <= btn_idx < len(self.buttons):
                self.set_mode(self.buttons[btn_idx]["id"])
            return

        self.start_x = event.x
        self.start_y = event.y

        if self.mode in ("rect", "ocr"):
            self.rect_id = self.canvas.create_rectangle(self.start_x, self.start_y, self.start_x, self.start_y, outline="#FFFFFF", width=2, fill="#FFFFFF")
            self.canvas.itemconfig(self.rect_id, stipple="gray25")
        elif self.mode == "lasso":
            self.lasso_points = [(event.x, event.y)]

    def on_drag(self, event):
        if not self.start_x or (self.tb_y <= self.start_y <= self.tb_y + self.tb_h and self.tb_x <= self.start_x <= self.tb_x + self.tb_w):
            return

        if self.mode in ("rect", "ocr"):
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)
        elif self.mode == "lasso":
            self.lasso_points.append((event.x, event.y))
            if len(self.lasso_points) > 1:
                p1, p2 = self.lasso_points[-2], self.lasso_points[-1]
                self.canvas.create_line(p1[0], p1[1], p2[0], p2[1], fill="#FFFFFF", width=3, capstyle=tk.ROUND, smooth=True)

    def on_release(self, event):
        if not self.start_x or (self.tb_y <= self.start_y <= self.tb_y + self.tb_h and self.tb_x <= self.start_x <= self.tb_x + self.tb_w):
            return

        x1, y1, x2, y2 = 0, 0, 0, 0
        if self.mode in ("rect", "ocr"):
            x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
            x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        elif self.mode == "lasso" and len(self.lasso_points) > 5:
            xs, ys = [p[0] for p in self.lasso_points], [p[1] for p in self.lasso_points]
            x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)

        if (x2 - x1) > 15 and (y2 - y1) > 15:
            # 1. Захоплюємо квадратну рамку
            bbox_img = self.screenshot.crop((x1, y1, x2, y2))
            
            # 2. Якщо це Ласо, створюємо маску
            if self.mode == "lasso":
                mask = Image.new("L", bbox_img.size, 0)
                draw = ImageDraw.Draw(mask)
                shifted_points = [(p[0]-x1, p[1]-y1) for p in self.lasso_points]
                draw.polygon(shifted_points, fill=255)
                
                # Заливаємо фон навколо виділення білим кольором
                final_img = Image.new("RGB", bbox_img.size, (255, 255, 255))
                final_img.paste(bbox_img, (0, 0), mask)
                self.result_img = final_img
            else:
                self.result_img = bbox_img
                
        self.cancel()

    def cancel(self, event=None):
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

is_running = False

def trigger():
    global is_running
    if is_running: return
    is_running = True
    try: OverlayUI()
    finally: is_running = False

keyboard.add_hotkey("alt+q", trigger)
keyboard.wait()