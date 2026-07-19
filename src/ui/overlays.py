"""Построение пиксмапов-оверлеев из данных areaflags (numpy -> QPixmap)."""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap

from core.areaflags import AreaFlags
from core.export import flag_rgba

# Цвета тиров по имени value-флага (RGB). Неизвестные имена получат цвета из запаски.
TIER_COLORS = {
    "Tier1": (76, 175, 80),      # зелёный
    "Tier2": (255, 235, 59),     # жёлтый
    "Tier3": (255, 152, 0),      # оранжевый
    "Tier4": (244, 67, 54),      # красный
    "Unique": (156, 39, 176),    # фиолетовый
}
FALLBACK_COLORS = [(0, 188, 212), (233, 30, 99), (121, 85, 72), (63, 81, 181)]

# Цвета usage-флагов по имени; неизвестным именам — запаска по золотому сечению оттенка.
USAGE_COLORS = {
    "Military": (229, 57, 53),        # красный
    "Police": (30, 136, 229),         # синий
    "Medic": (236, 64, 122),          # розовый
    "Firefighter": (255, 112, 67),    # оранж-красный
    "Industrial": (141, 110, 99),     # коричневый
    "Farm": (192, 202, 51),           # лаймовый
    "Coast": (38, 198, 218),          # циан
    "Town": (171, 71, 188),           # пурпурный
    "Village": (255, 167, 38),        # оранжевый
    "Hunting": (102, 187, 106),       # зелёный
    "Office": (92, 107, 192),         # индиго
    "School": (255, 238, 88),         # жёлтый
    "Prison": (120, 144, 156),        # серо-синий
    "Lunapark": (255, 138, 216),      # светло-розовый
    "SeasonalEvent": (255, 241, 118), # светло-жёлтый
    "ContaminatedArea": (124, 179, 66),  # ядовито-зелёный
    "Historical": (161, 136, 127),    # какао
    "Underground": (69, 90, 100),     # тёмный сине-серый
}


def usage_color(name: str, bit: int) -> tuple[int, int, int]:
    if name in USAGE_COLORS:
        return USAGE_COLORS[name]
    import colorsys
    h = (bit * 0.618033988749895) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 0.75, 0.95)
    return int(r * 255), int(g * 255), int(b * 255)


def tier_color(values: list[str], bit: int) -> tuple[int, int, int]:
    name = values[bit]
    if name in TIER_COLORS:
        return TIER_COLORS[name]
    return FALLBACK_COLORS[bit % len(FALLBACK_COLORS)]


def build_flag_pixmap(af: AreaFlags, name: str, color: tuple[int, int, int]) -> QPixmap:
    """Один битплан (usage или value) сплошным цветом; прозрачно вне флага."""
    rgba = flag_rgba(af, name, color)            # тот же массив уходит в экспорт PNG
    return _rgba_to_pixmap(rgba, af.grid_x, af.grid_y)


# дифф: где флаг появился в новом срезе / где пропал
DIFF_ADDED = (0, 230, 118)       # зелёный
DIFF_REMOVED = (255, 23, 68)     # красный


def build_diff_pixmap(added: np.ndarray, removed: np.ndarray) -> QPixmap:
    """Оверлей диффа одного флага: зелёное — появилось, красное — пропало."""
    h, w = added.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[added] = (*DIFF_ADDED, 255)
    rgba[removed] = (*DIFF_REMOVED, 255)
    rgba = np.ascontiguousarray(rgba[::-1])      # юг снизу -> север сверху
    return _rgba_to_pixmap(rgba, w, h)


def rgba_to_pixmap(rgba: np.ndarray) -> QPixmap:
    """RGBA-массив (h, w, 4) -> QPixmap. Для готовых масок (проект CE Tool)."""
    h, w = rgba.shape[:2]
    return _rgba_to_pixmap(np.ascontiguousarray(rgba), w, h)


def _rgba_to_pixmap(rgba: np.ndarray, w: int, h: int) -> QPixmap:
    img = QImage(rgba.data, w, h, w * 4, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(img.copy())         # copy: numpy-буфер живёт только тут
