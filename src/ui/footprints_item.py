"""Слой контуров зданий одного obj-слоя: ориентированные прямоугольники footprint,
залитые цветом слоя. Форма и цвет — как у слоя «Объекты», но фигуры вместо точек.

Все прямоугольники слоя собраны в один QPainterPath (одна заливка на отрисовку —
на порядок дешевле поштучного рисования тысяч полигонов)."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

SELECT_COLOR = QColor(255, 64, 64)


class FootprintsItem(QGraphicsItem):
    """corners — (M, 4, 2) мировые углы (X, Z); indices — глобальные индексы инстансов
    (для подсветки выбранного здания)."""

    def __init__(self, corners: np.ndarray, world_size: int, margin: int,
                 color: tuple[int, int, int], indices: np.ndarray | None = None):
        super().__init__()
        self._world = world_size
        self._margin = margin
        self._color = QColor(*color)
        self._idx = indices
        self._fill_op = 1.0
        self._border_op = 1.0
        self._selected: int | None = None
        sx = margin + corners[:, :, 0]
        sy = margin + (world_size - corners[:, :, 1])
        self._sx, self._sy = sx, sy
        self._path = self._build_path(sx, sy)

    @staticmethod
    def _build_path(sx: np.ndarray, sy: np.ndarray) -> QPainterPath:
        path = QPainterPath()
        for k in range(len(sx)):
            poly = QPolygonF([QPointF(float(sx[k, j]), float(sy[k, j]))
                              for j in range(4)])
            path.addPolygon(poly)
            path.closeSubpath()
        return path

    def set_color(self, color: tuple[int, int, int]):
        self._color = QColor(*color)
        self.update()

    def set_fill_opacity(self, v: float):
        self._fill_op = v
        self.update()

    def set_border_opacity(self, v: float):
        self._border_op = v
        self.update()

    def set_selected(self, index: int | None):
        self._selected = index
        self.update()

    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        fill = QColor(self._color)
        fill.setAlpha(int(200 * self._fill_op))
        edge_color = QColor(self._color)
        edge_color.setAlpha(int(255 * self._border_op))
        edge = QPen(edge_color, 1)
        edge.setCosmetic(True)
        painter.setBrush(fill)
        painter.setPen(edge)
        painter.drawPath(self._path)
        if self._selected is not None:
            poly = QPolygonF([QPointF(float(self._sx[self._selected, j]),
                                      float(self._sy[self._selected, j]))
                              for j in range(4)])
            halo = QPen(QColor(255, 255, 255), 4)
            halo.setCosmetic(True)
            painter.setPen(halo)
            painter.setBrush(QColor(255, 255, 255, 0))
            painter.drawPolygon(poly)
            core = QPen(SELECT_COLOR, 2)
            core.setCosmetic(True)
            painter.setPen(core)
            painter.drawPolygon(poly)

    def local_of(self, global_index: int | None) -> int | None:
        """Глобальный индекс инстанса -> позиция в этом слое (или None)."""
        if global_index is None or self._idx is None:
            return None
        pos = np.flatnonzero(self._idx == global_index)
        return int(pos[0]) if len(pos) else None
