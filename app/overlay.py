import time
import math
import tkinter as tk
from PIL import ImageGrab, ImageEnhance, ImageTk

from app.config import (
    DIM_BRIGHTNESS,
    BORDER_GLOW_WIDTH,
    BORDER_ANIM_FRAMES,
    VALID_MODES,
    DEFAULT_MODE,
)
from app.win_api import get_virtual_screen_rect, get_primary_screen_size, is_escape_pressed
from app.graphics import (
    chaikin_smooth,
    render_rounded_pill,
    build_glow_border_frames,
    crop_lasso_with_context,
)
from app.actions import search_google_lens, copy_selection_image, recognize_and_copy_text


class OverlayUI:
    def __init__(
        self,
        master: tk.Tk,
        on_finish,
        initial_mode: str = DEFAULT_MODE,
        on_mode_change=None,
    ):
        self.master = master
        self.on_finish = on_finish
        self.on_mode_change = on_mode_change
        self.closed = False
        self.dragging = False
        self.after_ids = []

        self.vx, self.vy, self.sw, self.sh = get_virtual_screen_rect()

        try:
            self.screenshot = ImageGrab.grab(all_screens=True)
        except Exception:
            self.screenshot = ImageGrab.grab()

        self.dimmed = ImageEnhance.Brightness(self.screenshot).enhance(DIM_BRIGHTNESS)

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

        self.bg_photo = ImageTk.PhotoImage(self.dimmed)
        self.canvas.create_image(0, 0, anchor="nw", image=self.bg_photo)

        # Елементи підсвітки виділеної зони (Spotlight)
        self.sel_photo = None
        self.sel_img_id = self.canvas.create_image(0, 0, anchor="nw")
        self.lasso_glow_id = None
        self.lasso_core_id = None
        self.bracket_ids = []

        self.mode = initial_mode if initial_mode in VALID_MODES else DEFAULT_MODE
        self.start_x = 0
        self.start_y = 0
        self.lasso_points = []
        self.last_crop_box = None

        # Геометрія панелі інструментів One UI
        primary_w, _ = get_primary_screen_size()
        offset_x = abs(self.vx) if self.vx < 0 else 0
        self.tb_w = 224
        self.tb_h = 44
        self.tb_x = offset_x + (primary_w - self.tb_w) // 2
        self.tb_target_y = 22
        self.tb_y = -32
        self.btn_w = self.tb_w // 5

        self.buttons = [
            {"id": "rect", "cx": self.tb_x},
            {"id": "lasso", "cx": self.tb_x + self.btn_w},
            {"id": "copy", "cx": self.tb_x + self.btn_w * 2},
            {"id": "ocr", "cx": self.tb_x + self.btn_w * 3},
            {"id": "close", "cx": self.tb_x + self.btn_w * 4},
        ]
        initial_btn = next((b for b in self.buttons if b["id"] == self.mode), self.buttons[0])
        self.active_slider_x = float(initial_btn["cx"])

        self.icon_shapes = []
        self.border_ids = {}
        self.border_frame_idx = 0
        self.slider_animating = False
        self.entrance_step = 0

        self.setup_border_glow()
        self.render_toolbar()
        self.animate_entrance()
        self.animate_aura()
        self._poll_escape()

        for seq in ("<ButtonPress-1>", "<Any-ButtonPress-1>"):
            self.canvas.bind(seq, self.on_press)
        for seq in ("<B1-Motion>", "<Any-B1-Motion>"):
            self.canvas.bind(seq, self.on_drag)
        for seq in ("<ButtonRelease-1>", "<Any-ButtonRelease-1>"):
            self.canvas.bind(seq, self.on_release)

        self.canvas.bind("<ButtonPress-3>", self.close)
        for seq in ("<Escape>", "<Alt-Escape>", "<Any-Escape>"):
            self.win.bind(seq, self.close)
            self.canvas.bind(seq, self.close)

        self.win.bind("<Control-c>", self.quick_copy_current)
        self.win.bind("<Control-C>", self.quick_copy_current)

        # Швидке перемикання режимів цифрами 1-4
        for idx, mode_key in enumerate(VALID_MODES, start=1):
            self.win.bind(str(idx), lambda _e, m=mode_key: self.set_mode(m))

        self.win.lift()
        self.win.focus_force()

    def _poll_escape(self):
        if self.closed:
            return
        if is_escape_pressed():
            self.close()
            return
        self.schedule(20, self._poll_escape)

    def schedule(self, delay_ms: int, func):
        if not self.closed:
            aid = self.win.after(delay_ms, func)
            self.after_ids.append(aid)

    def setup_border_glow(self):
        bw = BORDER_GLOW_WIDTH
        self.border_frames = build_glow_border_frames(
            self.dimmed, self.sw, self.sh, bw=bw, num_frames=BORDER_ANIM_FRAMES
        )
        f0 = self.border_frames[0]
        self.border_ids["top"] = self.canvas.create_image(0, 0, anchor="nw", image=f0["top"])
        self.border_ids["bottom"] = self.canvas.create_image(0, self.sh - bw, anchor="nw", image=f0["bottom"])
        self.border_ids["left"] = self.canvas.create_image(0, 0, anchor="nw", image=f0["left"])
        self.border_ids["right"] = self.canvas.create_image(self.sw - bw, 0, anchor="nw", image=f0["right"])

    def animate_entrance(self):
        if self.closed:
            return
        total_frames = 7
        if self.entrance_step < total_frames:
            self.entrance_step += 1
            t = self.entrance_step / total_frames
            ease = 1 - (1 - t) ** 3
            new_y = int(-32 + (self.tb_target_y - (-32)) * ease)
            dy = new_y - self.tb_y
            self.tb_y = new_y
            self.canvas.move("ui", 0, dy)
            self.schedule(16, self.animate_entrance)
        else:
            if self.tb_y != self.tb_target_y:
                self.canvas.move("ui", 0, self.tb_target_y - self.tb_y)
                self.tb_y = self.tb_target_y
            self.render_toolbar()

    def animate_aura(self):
        if self.closed:
            return
        self.border_frame_idx = (self.border_frame_idx + 1) % len(self.border_frames)
        frame = self.border_frames[self.border_frame_idx]
        for side, item_id in self.border_ids.items():
            self.canvas.itemconfig(item_id, image=frame[side])
        self.schedule(45, self.animate_aura)

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
            shapes.append(
                self.round_rect(cx - 7, cy - 7, cx + 7, cy + 7, 3, outline=color, width=1.8, fill="")
            )
        elif btn_id == "lasso":
            shapes.append(
                self.canvas.create_line(
                    cx - 8, cy + 3, cx - 3, cy - 5, cx + 3, cy + 5, cx + 8, cy - 3,
                    smooth=True, fill=color, width=2.0, capstyle=tk.ROUND,
                )
            )
        elif btn_id == "copy":
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

    def render_toolbar(self):
        if self.closed:
            return
        self.canvas.delete("ui")
        self.icon_shapes.clear()

        crop_y1 = max(0, self.tb_y)
        crop_y2 = max(crop_y1 + self.tb_h, self.tb_y + self.tb_h)
        bg_slice = self.dimmed.crop((self.tb_x, crop_y1, self.tb_x + self.tb_w, crop_y2))
        if bg_slice.size != (self.tb_w, self.tb_h):
            bg_slice = bg_slice.resize((self.tb_w, self.tb_h))

        pill_img = render_rounded_pill(
            bg_slice,
            fill_rgba=(26, 26, 32, 240),
            border_rgba=(74, 74, 86, 255),
            radius=self.tb_h // 2,
        )
        self.tb_photo = ImageTk.PhotoImage(pill_img)
        self.tb_bg_id = self.canvas.create_image(self.tb_x, self.tb_y, anchor="nw", image=self.tb_photo, tags="ui")

        pad = 5
        self.slider = self.round_rect(
            self.active_slider_x + pad,
            self.tb_y + pad,
            self.active_slider_x + self.btn_w - pad,
            self.tb_y + self.tb_h - pad,
            16,
            fill="#3C3C46",
            outline="",
            tags="ui",
        )
        self.update_icon_colors()

    def set_mode(self, mode_id):
        if mode_id == "close":
            self.close()
            return
        if mode_id not in VALID_MODES:
            return

        self.mode = mode_id
        if self.on_mode_change:
            self.on_mode_change(mode_id)

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
            color = "#FFFFFF" if btn["id"] == self.mode else "#8E8E98"
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
            self.active_slider_x += diff * 0.32

        pad = 5
        self.canvas.delete(self.slider)
        self.slider = self.round_rect(
            self.active_slider_x + pad,
            self.tb_y + pad,
            self.active_slider_x + self.btn_w - pad,
            self.tb_y + self.tb_h - pad,
            16,
            fill="#3C3C46",
            outline="",
            tags="ui",
        )
        self.canvas.tag_raise(self.tb_bg_id)
        self.canvas.tag_raise(self.slider)
        for shape_id in self.icon_shapes:
            self.canvas.tag_raise(shape_id)

        if self.slider_animating:
            self.schedule(15, self.animate_slider)

    def draw_selection_brackets(self, x1, y1, x2, y2):
        for bid in self.bracket_ids:
            self.canvas.delete(bid)
        self.bracket_ids.clear()

        rect = self.canvas.create_rectangle(x1, y1, x2, y2, outline="#D0D7DE", width=1)
        self.bracket_ids.append(rect)

        blen = min(16, (x2 - x1) // 3, (y2 - y1) // 3)
        if blen >= 5:
            corners = [
                (x1, y1 + blen, x1, y1, x1 + blen, y1),
                (x2 - blen, y1, x2, y1, x2, y1 + blen),
                (x2, y2 - blen, x2, y2, x2 - blen, y2),
                (x1 + blen, y2, x1, y2, x1, y2 - blen),
            ]
            for pts in corners:
                line = self.canvas.create_line(*pts, fill="#FFFFFF", width=3, capstyle=tk.ROUND, joinstyle=tk.ROUND)
                self.bracket_ids.append(line)

        self.canvas.tag_raise("ui")

    def on_press(self, event):
        if self.closed:
            return

        if self.tb_y <= event.y <= self.tb_y + self.tb_h and self.tb_x <= event.x <= self.tb_x + self.tb_w:
            self.dragging = False
            btn_idx = (event.x - self.tb_x) // self.btn_w
            if 0 <= btn_idx < len(self.buttons):
                self.set_mode(self.buttons[btn_idx]["id"])
            return

        self.dragging = True
        self.start_x = event.x
        self.start_y = event.y
        self.last_crop_box = None

        for lid in (self.lasso_glow_id, self.lasso_core_id):
            if lid:
                self.canvas.delete(lid)
        self.lasso_glow_id = None
        self.lasso_core_id = None

        if self.mode == "lasso":
            self.lasso_points = [(event.x, event.y)]
            self.lasso_glow_id = self.canvas.create_line(
                event.x, event.y, event.x, event.y,
                fill="#4285F4", width=10, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True
            )
            self.lasso_core_id = self.canvas.create_line(
                event.x, event.y, event.x, event.y,
                fill="#E8F0FE", width=3.5, capstyle=tk.ROUND, joinstyle=tk.ROUND, smooth=True
            )

    def on_drag(self, event):
        if not self.dragging or self.closed:
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
            last_x, last_y = self.lasso_points[-1]
            if math.hypot(event.x - last_x, event.y - last_y) >= 2:
                self.lasso_points.append((event.x, event.y))
                if len(self.lasso_points) >= 2 and self.lasso_glow_id and self.lasso_core_id:
                    smoothed = chaikin_smooth(self.lasso_points, iterations=1, closed=False)
                    flat_coords = [coord for pt in smoothed for coord in pt]
                    self.canvas.coords(self.lasso_glow_id, *flat_coords)
                    self.canvas.coords(self.lasso_core_id, *flat_coords)
                    self.canvas.tag_raise("ui")

    def extract_selection(self, event=None):
        if self.mode in ("rect", "copy", "ocr"):
            ex = event.x if event else (self.last_crop_box[2] if self.last_crop_box else self.start_x)
            ey = event.y if event else (self.last_crop_box[3] if self.last_crop_box else self.start_y)
            x1 = max(0, min(self.start_x, ex))
            y1 = max(0, min(self.start_y, ey))
            x2 = min(self.sw, max(self.start_x, ex))
            y2 = min(self.sh, max(self.start_y, ey))
            if (x2 - x1) > 12 and (y2 - y1) > 12:
                return self.screenshot.crop((x1, y1, x2, y2)), (x1, y1, x2, y2)

        elif self.mode == "lasso":
            return crop_lasso_with_context(self.screenshot, self.lasso_points, self.sw, self.sh)

        return None, None

    def quick_copy_current(self, event=None):
        img, _ = self.extract_selection() if self.dragging else (None, None)
        self.close()
        if img:
            copy_selection_image(self.master, img)

    def on_release(self, event):
        if not self.dragging or self.closed:
            return
        self.dragging = False

        result_img = None
        current_mode = self.mode
        try:
            result_img, box = self.extract_selection(event)
            if result_img and current_mode == "lasso" and box:
                self.sel_photo = ImageTk.PhotoImage(result_img)
                self.canvas.coords(self.sel_img_id, box[0], box[1])
                self.canvas.itemconfig(self.sel_img_id, image=self.sel_photo)
                self.canvas.tag_raise("ui")
                self.win.update()
                time.sleep(0.08)
        finally:
            self.close()

        if result_img:
            if current_mode in ("rect", "lasso"):
                search_google_lens(self.master, result_img)
            elif current_mode == "copy":
                copy_selection_image(self.master, result_img)
            elif current_mode == "ocr":
                recognize_and_copy_text(self.master, result_img)

    def close(self, event=None):
        if self.closed:
            return
        self.closed = True
        self.dragging = False

        for aid in self.after_ids:
            try:
                self.win.after_cancel(aid)
            except Exception:
                pass
        self.after_ids.clear()

        try:
            self.win.withdraw()
            self.win.destroy()
            self.master.update_idletasks()
        except Exception:
            pass

        self.on_finish()