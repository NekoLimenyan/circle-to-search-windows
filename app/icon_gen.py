import os
import math
from PIL import Image, ImageDraw
from app.graphics import sample_google_rgb


def generate_lens_icon(ico_path: str) -> str:
    """Генерує .ico файл із лупою в градієнтних кольорах Google та підкладкою One UI."""
    os.makedirs(os.path.dirname(os.path.abspath(ico_path)), exist_ok=True)

    size = 512  # Рендер у 2x для ідеального антиаліасингу
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Темна заокруглена основа (One UI Squircle)
    pad = 28
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=116,
        fill=(28, 28, 36, 255),
        outline=(68, 68, 82, 255),
        width=8,
    )

    # Геометрія лупи
    cx, cy = 228, 228
    r_outer = 112
    ring_w = 28

    # 2. Ручка лупи (45° вниз-праворуч)
    angle = math.radians(45)
    cos_a, sin_a = math.cos(angle), math.sin(angle)
    h_start = r_outer - 4
    h_end = r_outer + 96
    x1, y1 = cx + h_start * cos_a, cy + h_start * sin_a
    x2, y2 = cx + h_end * cos_a, cy + h_end * sin_a

    handle_color = (232, 234, 240, 255)
    draw.line([(x1, y1), (x2, y2)], fill=handle_color, width=32)
    cap_r = 16
    draw.ellipse([x2 - cap_r, y2 - cap_r, x2 + cap_r, y2 + cap_r], fill=handle_color)

    # 3. Внутрішнє скло лінзи з легким відблиском
    r_inner = r_outer - ring_w + 4
    draw.ellipse(
        [cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner],
        fill=(55, 75, 115, 75),
    )
    draw.arc(
        [cx - r_inner + 18, cy - r_inner + 18, cx + r_inner - 18, cy + r_inner - 18],
        start=200,
        end=265,
        fill=(255, 255, 255, 110),
        width=10,
    )

    # 4. Градієнтне кільце Google (сегменти по 3°)
    bbox = [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer]
    step = 3
    for deg in range(0, 360, step):
        rgb = sample_google_rgb(deg / 360.0)
        draw.arc(bbox, start=deg - 1, end=deg + step + 1, fill=(*rgb, 255), width=ring_w)

    icon_256 = img.resize((256, 256), Image.Resampling.LANCZOS)
    icon_256.save(
        ico_path,
        format="ICO",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    return ico_path