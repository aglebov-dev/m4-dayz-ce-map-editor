"""Построение пиксмапов-оверлеев из данных areaflags (numpy -> QPixmap)."""
from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage, QPixmap

from core.areaflags import AreaFlags
from core.export import flag_rgba

# Палитра и подбор цвета флага вынесены в common.palette (Qt-free). Реэкспорт — чтобы
# существующие `from ui.overlays import tier_color, usage_color` не сломались.
from common.palette import (  # noqa: F401
    FALLBACK_COLORS, TIER_COLORS, USAGE_COLORS, tier_color, usage_color,
)


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
