#!/usr/bin/env python3
"""Генератор иконок семейства M4 (вариант «Объём»).

Векторно-плоская отрисовка через Pillow (без внешних зависимостей): градиентная
squircle-плитка + верхний блик + монограмма с лёгкой тенью. Для мелких размеров
(32/16) используется своя отрисовка «M4 крупно + плашка» — так иконка остаётся
читаемой в трее и заголовке окна. Всё склеивается в мультиразмерный .ico.

Запуск:  python create_icon.py
Выход:   app_icon.png, app_icon.ico, app_icon_high.ico  (M4 CE)
         brand/m4-crm/app_icon.png, app_icon.ico         (M4 CRM)
"""
from __future__ import annotations

import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# --- палитра семейства M4 ---
GRAD_TOP = (255, 157, 61)      # #FF9D3D
GRAD_BOT = (228, 103, 14)      # #E4670E
MAROON = (142, 28, 16)         # #8E1C10 — первая строка (M4)
WHITE = (255, 255, 255)        # вторая строка

RADIUS_FRAC = 0.23             # скругление плитки (squircle-подобное)
SS = 4                         # суперсэмплинг для гладких краёв

FONT_CANDIDATES = [
    "C:/Windows/Fonts/segoeuib.ttf",   # Segoe UI Bold (как в макете)
    "C:/Windows/Fonts/arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(px: int) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return ImageFont.truetype(path, px)
    return ImageFont.load_default()


def _fit_font(text: str, target_w: float, start_px: int) -> ImageFont.FreeTypeFont:
    """Подобрать размер шрифта так, чтобы `text` влез в target_w по ширине."""
    px = start_px
    while px > 8:
        f = _font(px)
        w = f.getbbox(text)[2] - f.getbbox(text)[0]
        if w <= target_w:
            return f
        px -= 2
    return _font(px)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _gradient_tile(size: int) -> Image.Image:
    """Оранжевая плитка: вертикальный градиент + мягкий верхний блик."""
    t = np.linspace(0.0, 1.0, size, dtype=np.float32)[:, None]        # 0 сверху → 1 снизу
    top = np.array(GRAD_TOP, np.float32)
    bot = np.array(GRAD_BOT, np.float32)
    rgb = (top[None, None, :] * (1 - t[..., None]) + bot[None, None, :] * t[..., None])
    rgb = np.repeat(rgb, size, axis=1)                               # (h, w, 3)

    # радиальный блик из верхнего центра
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    d = np.sqrt(((xx - size / 2) / (size * 0.95)) ** 2 + ((yy - 0) / (size * 0.95)) ** 2)
    hi = np.clip(1.0 - d / 0.6, 0.0, 1.0) ** 1.5 * 0.28              # альфа блика
    rgb = rgb + (255.0 - rgb) * hi[..., None]

    return Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8), "RGB")


def _draw_two_lines(img: Image.Image, l1: str, l2: str) -> None:
    """Монограмма по центру: строка 1 (бордо) сверху, строка 2 (белая) снизу, с тенью."""
    size = img.width
    cx = size / 2
    cy1, cy2 = size * 0.335, size * 0.725
    f1 = _fit_font(l1, size * 0.80, int(size * 0.42))
    f2 = _fit_font(l2, size * 0.80, int(size * 0.42))

    # тень (мягкая, тёмно-бордовая, со сдвигом вниз)
    shadow = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    off = size * 0.012
    sd.text((cx + off, cy1 + off), l1, font=f1, fill=(58, 13, 5, 150), anchor="mm")
    sd.text((cx + off, cy2 + off), l2, font=f2, fill=(58, 13, 5, 130), anchor="mm")
    shadow = shadow.filter(ImageFilter.GaussianBlur(size * 0.012))
    img.paste(shadow, (0, 0), shadow)

    d = ImageDraw.Draw(img)
    d.text((cx, cy1), l1, font=f1, fill=MAROON, anchor="mm")
    d.text((cx, cy2), l2, font=f2, fill=WHITE, anchor="mm")


def _draw_focus(img: Image.Image, main: str, sub: str, *, pill: bool = True) -> None:
    """Мелкий размер: «M4» крупно. С плашкой-подписью (32 px) или без неё (16 px:
    подпись всё равно нечитаема, поэтому просто крупная «M4» во всю плитку)."""
    size = img.width
    cx = size / 2
    d = ImageDraw.Draw(img)
    if not pill:
        fm = _fit_font(main, size * 0.90, int(size * 0.74))
        d.text((cx, size * 0.50), main, font=fm, fill=MAROON, anchor="mm")
        return

    fm = _fit_font(main, size * 0.86, int(size * 0.60))
    d.text((cx, size * 0.40), main, font=fm, fill=MAROON, anchor="mm")
    fs = _fit_font(sub, size * 0.60, int(size * 0.16))
    tb = d.textbbox((cx, size * 0.80), sub, font=fs, anchor="mm")
    pad_x, pad_y = size * 0.06, size * 0.035
    box = [tb[0] - pad_x, tb[1] - pad_y, tb[2] + pad_x, tb[3] + pad_y]
    d.rounded_rectangle(box, radius=(box[3] - box[1]) / 2, fill=WHITE)
    d.text((cx, size * 0.80), sub, font=fs, fill=GRAD_BOT, anchor="mm")


def render(size: int, l1: str, l2: str, *, focus: bool, pill: bool = True) -> Image.Image:
    """Готовая RGBA-иконка нужного размера (суперсэмплинг + скругление)."""
    S = size * SS
    tile = _gradient_tile(S).convert("RGBA")
    if focus:
        _draw_focus(tile, l1, l2, pill=pill)
    else:
        _draw_two_lines(tile, l1, l2)
    tile.putalpha(_rounded_mask(S, int(S * RADIUS_FRAC)))
    return tile.resize((size, size), Image.Resampling.LANCZOS)


def build(l1: str, l2: str, out_png: str, out_ico: str, *, hi_ico: str | None = None) -> None:
    """Собрать PNG (512) + мультиразмерный ICO: крупно — монограмма, мелко — «M4»-фокус."""
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    render(512, l1, l2, focus=False).save(out_png, "PNG")

    layers = {s: render(s, l1, l2, focus=False) for s in (256, 128, 64, 48)}
    layers[32] = render(32, l1, l2, focus=True, pill=True)     # M4 + плашка
    layers[16] = render(16, l1, l2, focus=True, pill=False)    # только M4
    imgs = [layers[s] for s in (256, 128, 64, 48, 32, 16)]
    for path in filter(None, (out_ico, hi_ico)):
        imgs[0].save(path, format="ICO", append_images=imgs[1:],
                     sizes=[(i.width, i.width) for i in imgs])
    print(f"  {out_png}  +  {out_ico}" + (f"  +  {hi_ico}" if hi_ico else ""))


def main() -> None:
    print("M4 CE  →")
    build("M4", "CE", "app_icon.png", "app_icon.ico", hi_ico="app_icon_high.ico")
    print("M4 CRM →")
    build("M4", "CRM", "brand/m4-crm/app_icon.png", "brand/m4-crm/app_icon.ico")
    print("Готово.")


if __name__ == "__main__":
    main()
