"""Круги территорий животных одного слоя: контур в мировом радиусе + лёгкая заливка.
Радиусы реальные (метры сцены), поэтому круги масштабируются вместе с картой."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem


class TerritoriesItem(QGraphicsItem):
    def __init__(self, x, z, r, world_size: int, margin: int,
                 color: tuple[int, int, int]):
        super().__init__()
        self._world = world_size
        self._margin = margin
        self._color = QColor(*color)
        # в сцену: x вправо, север сверху (z=0 = юг -> y = world - z)
        self._cx = margin + np.asarray(x, dtype=np.float64)
        self._cy = margin + (world_size - np.asarray(z, dtype=np.float64))
        self._r = np.asarray(r, dtype=np.float64)

    def set_color(self, color: tuple[int, int, int]):
        self._color = QColor(*color)
        self.update()

    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self._color, 2)
        pen.setCosmetic(True)                    # 2 px обводки при любом зуме
        painter.setPen(pen)
        fill = QColor(self._color)
        fill.setAlpha(40)
        painter.setBrush(fill)
        for cx, cy, r in zip(self._cx, self._cy, self._r):
            painter.drawEllipse(QPointF(float(cx), float(cy)), float(r), float(r))
