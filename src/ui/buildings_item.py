"""Слой точек зданий одного obj-слоя. Без кластеризации: все точки рисуются всегда —
рендер всей карты быстрый, а группировка мешала выбору отдельного здания."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

SELECT_COLOR = QColor(255, 64, 64)


class BuildingsItem(QGraphicsItem):
    """Точки одного слоя зданий; размер точки — в экранных px (косметическое перо)."""

    def __init__(self, x: np.ndarray, z: np.ndarray, world_size: int, margin: int,
                 color: tuple[int, int, int]):
        super().__init__()
        self._color = QColor(*color)
        self._world = world_size
        self._margin = margin
        self._opacity_pts = 1.0
        sx = margin + x
        sy = margin + (world_size - z)
        self._points = QPolygonF([QPointF(float(a), float(b)) for a, b in zip(sx, sy)])
        self._sx, self._sy = sx, sy
        self._selected: int | None = None

    def set_selected(self, index: int | None):
        self._selected = index
        self.update()

    def set_color(self, color: tuple[int, int, int]):
        self._color = QColor(*color)
        self.update()

    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        size = 4 if lod < 0.6 else 6 if lod < 1.0 else 9
        pen = QPen(self._color, size)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.drawPoints(self._points)
        if self._selected is not None:
            p = QPointF(float(self._sx[self._selected]),
                        float(self._sy[self._selected]))
            halo = QPen(QColor(255, 255, 255), size + 8)
            halo.setCosmetic(True)
            painter.setPen(halo)
            painter.drawPoint(p)
            core = QPen(SELECT_COLOR, size + 4)
            core.setCosmetic(True)
            painter.setPen(core)
            painter.drawPoint(p)
