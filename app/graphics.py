import math
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat, ImageTk
from app.config import GOOGLE_STOPS, DIM_BRIGHTNESS, LASSO_PADDING


def sample_google_rgb(t: float):
    """Повертає (R, G, B) у точці t ∈ [0, 1) плавного градієнта Google."""
    t = t % 1.0
    n = len(GOOGLE_STOPS)
    scaled = t * n
    idx = int(scaled)
    frac = scaled - idx
    smooth_frac = 0.5 - 0.5 * math.cos(frac * math.pi)
    c1 = GOOGLE_STOPS[idx % n]
    c2 = GOOGLE_STOPS[(idx + 1) % n]
    return (
        int(c1[0] + (c2[0] - c1[0]) * smooth_frac),
        int(c1[1] + (c2[1] - c1[1]) * smooth_frac),
        int(c1[2] + (c2[2] - c1[2]) * smooth_frac),
    )


def chaikin_smooth(points, iterations: int = 2, closed: bool = False):
    """Згладжує ламану лінію миші в плавну криву (алгоритм Чайкіна)."""
    if len(points) < 3:
        return points
    pts = list(points)
    for _ in range(iterations):
        new_pts = []
        count = len(pts)
        limit = count if closed else count - 1
        if not closed:
            new_pts.append(pts[0])
        for i in range(limit):
            p0 = pts[i]
            p1 = pts[(i + 1) % count]
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])
            new_pts.append(q)
            new_pts.append(r)
        if not closed:
            new_pts.append(pts[-1])
        pts = new_pts
    return pts


def render_rounded_pill(bg_crop: Image.Image, fill_rgba, border_rgba, radius: int) -> Image.Image:
    """Рендерить згладжену One UI капсулу тулбару поверх фону (2x supersampling)."""
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


def build_glow_border_frames(dimmed_bg: Image.Image, sw: int, sh: int, bw: int = 6, num_frames: int = 20):
    """Генерує кадри анімованого світіння Google по периметру екрана."""
    perimeter = 2 * sw + 2 * sh
    raw = bytearray()
    for i in range(perimeter * 2):
        r, g, b = sample_google_rgb((i % perimeter) / perimeter)
        raw.extend((r, g, b))
    grad_1d = Image.frombytes("RGB", (perimeter * 2, 1), bytes(raw))

    alphas = [245, 215, 160, 100, 48, 16][:bw]
    while len(alphas) < bw:
        alphas.append(12)

    mask_top = Image.frombytes("L", (1, bw), bytes(alphas)).resize((sw, bw), Image.Resampling.NEAREST)
    mask_bottom = Image.frombytes("L", (1, bw), bytes(reversed(alphas))).resize((sw, bw), Image.Resampling.NEAREST)
    mask_left = Image.frombytes("L", (bw, 1), bytes(alphas)).resize((bw, sh), Image.Resampling.NEAREST)
    mask_right = Image.frombytes("L", (bw, 1), bytes(reversed(alphas))).resize((bw, sh), Image.Resampling.NEAREST)

    bg_top = dimmed_bg.crop((0, 0, sw, bw))
    bg_bottom = dimmed_bg.crop((0, sh - bw, sw, sh))
    bg_left = dimmed_bg.crop((0, 0, bw, sh))
    bg_right = dimmed_bg.crop((sw - bw, 0, sw, sh))

    frames = []
    for f in range(num_frames):
        shift = int((f / num_frames) * perimeter)

        g_top = grad_1d.crop((shift, 0, shift + sw, 1)).resize((sw, bw), Image.Resampling.NEAREST)
        s1 = shift + sw
        g_right = (
            grad_1d.crop((s1, 0, s1 + sh, 1))
            .transpose(Image.Transpose.ROTATE_270)
            .resize((bw, sh), Image.Resampling.NEAREST)
        )
        s2 = shift + sw + sh
        g_bottom = (
            grad_1d.crop((s2, 0, s2 + sw, 1))
            .transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            .resize((sw, bw), Image.Resampling.NEAREST)
        )
        s3 = shift + 2 * sw + sh
        g_left = (
            grad_1d.crop((s3, 0, s3 + sh, 1))
            .transpose(Image.Transpose.ROTATE_90)
            .resize((bw, sh), Image.Resampling.NEAREST)
        )

        frames.append({
            "top": ImageTk.PhotoImage(Image.composite(g_top, bg_top, mask_top)),
            "right": ImageTk.PhotoImage(Image.composite(g_right, bg_right, mask_right)),
            "bottom": ImageTk.PhotoImage(Image.composite(g_bottom, bg_bottom, mask_bottom)),
            "left": ImageTk.PhotoImage(Image.composite(g_left, bg_left, mask_left)),
        })
    return frames


def crop_lasso_with_context(screenshot: Image.Image, lasso_points, sw: int, sh: int, pad: int = LASSO_PADDING):
    """Вирізає обведену область зі згладженим контуром та розмитим контекстним фоном."""
    if len(lasso_points) < 3:
        return None, None

    closed_curve = chaikin_smooth(lasso_points, iterations=2, closed=True)
    xs = [p[0] for p in closed_curve]
    ys = [p[1] for p in closed_curve]

    x1 = max(0, int(min(xs)) - pad)
    y1 = max(0, int(min(ys)) - pad)
    x2 = min(sw, int(max(xs)) + pad)
    y2 = min(sh, int(max(ys)) + pad)

    if (x2 - x1) <= 16 or (y2 - y1) <= 16:
        return None, None

    sharp_crop = screenshot.crop((x1, y1, x2, y2))
    w, h = sharp_crop.size

    context_bg = sharp_crop.filter(ImageFilter.GaussianBlur(radius=7))
    context_bg = ImageEnhance.Brightness(context_bg).enhance(DIM_BRIGHTNESS)

    scale = 4
    hi_mask = Image.new("L", (w * scale, h * scale), 0)
    draw = ImageDraw.Draw(hi_mask)
    shifted = [((p[0] - x1) * scale, (p[1] - y1) * scale) for p in closed_curve]
    draw.polygon(shifted, fill=255)

    smooth_mask = hi_mask.resize((w, h), Image.Resampling.LANCZOS)
    smooth_mask = smooth_mask.filter(ImageFilter.GaussianBlur(radius=1.5))

    final_img = Image.composite(sharp_crop, context_bg, smooth_mask)
    return final_img, (x1, y1, x2, y2)


def prepare_image_for_ocr(image: Image.Image, high_contrast: bool = False) -> Image.Image:
    """Готує вирізане зображення до OCR: апскейл дрібного шрифту, поля та інверсія темного фону."""
    img = image.convert("RGB")
    w, h = img.size

    # Windows OCR потребує висоту літер від ~22 px; дрібні фрагменти масштабуємо
    if h < 55 or w < 140:
        scale = 3
    elif h < 150 or w < 360:
        scale = 2
    else:
        scale = 1

    if scale > 1:
        img = img.resize((w * scale, h * scale), Image.Resampling.LANCZOS)

    if high_contrast:
        gray = img.convert("L")
        mean_luma = ImageStat.Stat(gray).mean[0]
        # Темний інтерфейс (наприклад, VS Code) перетворюємо на чорний текст по світлому фону
        if mean_luma < 115:
            gray = ImageOps.invert(gray)
        gray = ImageOps.autocontrast(gray, cutoff=1)
        gray = gray.filter(ImageFilter.SHARPEN)
        img = gray.convert("RGB")

    # Визначаємо фоновий колір по кутах і додаємо відступ 24 px навколо тексту
    pw, ph = img.size
    corners = [
        img.getpixel((0, 0)),
        img.getpixel((pw - 1, 0)),
        img.getpixel((0, ph - 1)),
        img.getpixel((pw - 1, ph - 1)),
    ]
    bg_color = tuple(sum(c[i] for c in corners) // 4 for i in range(3))
    return ImageOps.expand(img, border=24, fill=bg_color)