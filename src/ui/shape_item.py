"""Контур фигуры на карте: пунктир + ручки. Сам ничего не заливает — это превью,
которое пользователь правит, а применяет заливку главное окно по Enter.

Координаты — сцены (пиксели полного зума). Ручки рисуются экранного размера, чтобы
их можно было ухватить на любом зуме."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

HANDLE_PX = 8
GRAB_PX = 10
MAX_HANDLES = 40


class ShapeItem(QGraphicsItem):
    """kind: 'rect' | 'ellipse' | 'polygon'. Для rect/ellipse points = 2 угла bbox,
    для polygon — вершины. building=True — контур ещё строится (полигон кликами)."""

    def __init__(self, kind: str, points: list[QPointF], world_size: int, margin: int):
        super().__init__()
        self.kind = kind
        self.points = list(points)
        self.building = False
        self.cursor: QPointF | None = None
        self._world = world_size
        self._margin = margin
        self.setZValue(55)


    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)

    def rect(self) -> QRectF:
        return QRectF(self.points[0], self.points[1]).normalized()

    def handles(self) -> list[QPointF]:
        """Точки-ручки. У rect/ellipse — 4 угла + 4 середины сторон."""
        if self.kind == "polygon":
            return [] if len(self.points) > MAX_HANDLES else list(self.points)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        return [QPointF(r.left(), r.top()), QPointF(cx, r.top()),
                QPointF(r.right(), r.top()), QPointF(r.right(), cy),
                QPointF(r.right(), r.bottom()), QPointF(cx, r.bottom()),
                QPointF(r.left(), r.bottom()), QPointF(r.left(), cy)]

    def handle_at(self, pos: QPointF, lod: float) -> int:
        """Индекс БЛИЖАЙШЕЙ ручки под точкой сцены (-1 — мимо). lod: масштаб вью.
        Именно ближайшей: на отдалении зона захвата больше самой фигуры, и «первая
        подходящая» хватала не ту ручку."""
        grab = GRAB_PX / max(lod, 1e-6)
        best, best_d2 = -1, grab * grab
        for i, h in enumerate(self.handles()):
            d2 = (h.x() - pos.x()) ** 2 + (h.y() - pos.y()) ** 2
            if d2 <= best_d2:
                best, best_d2 = i, d2
        return best

    def contains_point(self, pos: QPointF) -> bool:
        """Точка внутри контура — значит тащим фигуру целиком."""
        if self.kind == "polygon":
            return QPolygonF(self.points).containsPoint(pos, Qt.FillRule.OddEvenFill)
        return self.rect().contains(pos)

    def move_handle(self, i: int, pos: QPointF):
        if self.kind == "polygon":
            if 0 <= i < len(self.points):
                self.points[i] = pos
            self.update()
            return
        r = self.rect()
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        if i in (0, 6, 7):
            left = pos.x()
        if i in (2, 3, 4):
            right = pos.x()
        if i in (0, 1, 2):
            top = pos.y()
        if i in (4, 5, 6):
            bottom = pos.y()
        self.points = [QPointF(left, top), QPointF(right, bottom)]
        self.update()

    def move_by(self, dx: float, dy: float):
        self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]
        self.update()

    def set_second(self, pos: QPointF):
        """Растягивание при создании rect/ellipse."""
        self.points = [self.points[0], pos]
        self.update()

    def add_point(self, pos: QPointF):
        self.points.append(pos)
        self.update()

    def is_degenerate(self) -> bool:
        """Линия, а не фигура — заливать нечего."""
        if self.kind == "polygon":
            if len(self.points) < 3:
                return True
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            return (max(xs) - min(xs) < 1.0) or (max(ys) - min(ys) < 1.0)
        r = self.rect()
        return r.width() < 1.0 or r.height() < 1.0

    def world_points(self) -> list[tuple[float, float]]:
        """Сцена -> мировые метры (юг = 0)."""
        return [(p.x() - self._margin, self._world - (p.y() - self._margin))
                for p in self.points]


    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(255, 255, 255, 40))
        if self.kind == "rect":
            painter.drawRect(self.rect())
        elif self.kind == "ellipse":
            painter.drawEllipse(self.rect())
        else:
            poly = QPolygonF(self.points)
            if self.building:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(poly)
                if self.cursor is not None and self.points:
                    painter.drawLine(self.points[-1], self.cursor)
            else:
                painter.drawPolygon(poly)
        for h in self.handles():
            painter.save()
            painter.translate(h)
            painter.scale(1.0 / lod, 1.0 / lod)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawRect(QRectF(-HANDLE_PX / 2, -HANDLE_PX / 2,
                                    HANDLE_PX, HANDLE_PX))
            painter.restore()
