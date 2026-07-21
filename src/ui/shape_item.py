"""Контур фигуры на карте: пунктир + ручки. Сам ничего не заливает — это превью,
которое пользователь правит, а применяет заливку главное окно по Пробелу.

Координаты — сцены (пиксели полного зума). Ручки рисуются экранного размера, чтобы
их можно было ухватить на любом зуме.

Поворот. У rect/ellipse хранится УГОЛ (`angle`, градусы по часовой на экране), а points
остаются осевым bbox в локальной системе фигуры — иначе после поворота нельзя было бы
тянуть стороны. У polygon/lasso угла нет: поворот сразу переписывает вершины, потому что
для них форма и есть список точек."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

HANDLE_PX = 8            # сторона ручки на экране
GRAB_PX = 10             # радиус захвата ручки курсором
ROTATE_PX = 26           # вынос ручки поворота над верхом фигуры, экранные px
ROTATE_R_PX = 5          # радиус кружка-ручки поворота
SNAP_DEG = 15            # шаг привязки угла при зажатом Shift
# больше вершин — ручки не рисуем: у лассо их сотни, это была бы каша
MAX_HANDLES = 40


def _rotate_around(point: QPointF, centre: QPointF, degrees: float) -> QPointF:
    """Повернуть точку вокруг центра. Угол — по часовой на экране (ось y вниз)."""
    if not degrees:
        return QPointF(point)
    rad = math.radians(degrees)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    dx, dy = point.x() - centre.x(), point.y() - centre.y()
    return QPointF(centre.x() + dx * cos_a - dy * sin_a,
                   centre.y() + dx * sin_a + dy * cos_a)


class ShapeItem(QGraphicsItem):
    """kind: 'rect' | 'ellipse' | 'polygon'. Для rect/ellipse points = 2 угла bbox,
    для polygon — вершины. building=True — контур ещё строится (полигон кликами)."""

    def __init__(self, kind: str, points: list[QPointF], world_size: int, margin: float):
        super().__init__()
        self.kind = kind
        self.points = list(points)
        self.building = False
        self.angle = 0.0                         # градусы, по часовой на экране
        self.cursor: QPointF | None = None       # «резиновая» линия при построении
        self._world = world_size
        self._margin = margin
        self._rotate_from: tuple[float, float, list[QPointF], QPointF] | None = None
        self.setZValue(55)                       # над оверлеями, под курсором кисти

    # ---------- геометрия ----------

    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)                # не мельчим: перерисовка и так редкая

    def rect(self) -> QRectF:
        """bbox БЕЗ поворота (локальная система фигуры)."""
        return QRectF(self.points[0], self.points[1]).normalized()

    def centre(self) -> QPointF:
        """Центр вращения: у rect/ellipse — центр bbox, у полигона — центр его габаритов."""
        if self.kind == "polygon":
            if not self.points:
                return QPointF(0, 0)
            xs = [p.x() for p in self.points]
            ys = [p.y() for p in self.points]
            return QPointF((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
        return self.rect().center()

    def _to_local(self, pos: QPointF) -> QPointF:
        """Точка сцены -> система фигуры до поворота (для попаданий и правки сторон)."""
        return _rotate_around(pos, self.centre(), -self.angle)

    def handles(self, lod: float = 1.0) -> list[QPointF]:
        """Точки-ручки в координатах сцены. У rect/ellipse — 4 угла + 4 середины сторон,
        у полигона — вершины. ПОСЛЕДНЯЯ ручка всегда поворотная (см. `rotate_index`)."""
        return self._shape_handles() + [self._rotate_handle(lod)]

    def _shape_handles(self) -> list[QPointF]:
        if self.kind == "polygon":
            return [] if len(self.points) > MAX_HANDLES else list(self.points)
        r = self.rect()
        cx, cy = r.center().x(), r.center().y()
        corners = [QPointF(r.left(), r.top()), QPointF(cx, r.top()),
                   QPointF(r.right(), r.top()), QPointF(r.right(), cy),
                   QPointF(r.right(), r.bottom()), QPointF(cx, r.bottom()),
                   QPointF(r.left(), r.bottom()), QPointF(r.left(), cy)]
        return [_rotate_around(p, r.center(), self.angle) for p in corners]

    def _top_centre(self) -> QPointF:
        """Середина верхней стороны — от неё растёт «стебель» ручки поворота."""
        if self.kind == "polygon":
            centre = self.centre()
            top = min((p.y() for p in self.points), default=centre.y())
            return QPointF(centre.x(), top)
        r = self.rect()
        return _rotate_around(QPointF(r.center().x(), r.top()), r.center(), self.angle)

    def _rotate_handle(self, lod: float) -> QPointF:
        """Ручка поворота: вынесена над фигурой на постоянное ЭКРАННОЕ расстояние."""
        top = self._top_centre()
        offset = ROTATE_PX / max(lod, 1e-6)
        return _rotate_around(QPointF(top.x(), top.y() - offset), top, self.angle)

    def rotate_index(self) -> int:
        """Индекс поворотной ручки в списке `handles()`."""
        return len(self._shape_handles())

    def handle_at(self, pos: QPointF, lod: float) -> int:
        """Индекс БЛИЖАЙШЕЙ ручки под точкой сцены (-1 — мимо). lod: масштаб вью.
        Именно ближайшей: на отдалении зона захвата больше самой фигуры, и «первая
        подходящая» хватала не ту ручку."""
        grab = GRAB_PX / max(lod, 1e-6)
        best, best_d2 = -1, grab * grab
        for i, h in enumerate(self.handles(lod)):
            d2 = (h.x() - pos.x()) ** 2 + (h.y() - pos.y()) ** 2
            if d2 <= best_d2:
                best, best_d2 = i, d2
        return best

    def edge_at(self, pos: QPointF, lod: float) -> int:
        """Индекс вершины, ПОСЛЕ которой лежит ближайшее ребро под курсором (-1 — мимо).
        Только для полигона: клик по ребру добавляет туда вершину."""
        if self.kind != "polygon" or len(self.points) < 2:
            return -1
        grab = GRAB_PX / max(lod, 1e-6)
        best, best_d2 = -1, grab * grab
        for i, start in enumerate(self.points):
            end = self.points[(i + 1) % len(self.points)]
            d2 = _distance_to_segment_sq(pos, start, end)
            if d2 <= best_d2:
                best, best_d2 = i, d2
        return best

    def contains_point(self, pos: QPointF) -> bool:
        """Точка внутри контура — значит тащим фигуру целиком."""
        if self.kind == "polygon":
            return QPolygonF(self.points).containsPoint(pos, Qt.FillRule.OddEvenFill)
        return self.rect().contains(self._to_local(pos))

    def move_handle(self, i: int, pos: QPointF):
        """Тянем ручку. У повёрнутых rect/ellipse считаем в локальной системе, а центр
        сдвигаем так, чтобы противоположная сторона осталась на месте на экране."""
        if self.kind == "polygon":
            if 0 <= i < len(self.points):
                self.points[i] = pos
            self.update()
            return
        centre = self.rect().center()
        local = self._to_local(pos)
        r = self.rect()
        left, top, right, bottom = r.left(), r.top(), r.right(), r.bottom()
        if i in (0, 6, 7):
            left = local.x()
        if i in (2, 3, 4):
            right = local.x()
        if i in (0, 1, 2):
            top = local.y()
        if i in (4, 5, 6):
            bottom = local.y()
        new_rect = QRectF(QPointF(left, top), QPointF(right, bottom))
        # центр bbox уехал; в повёрнутой системе тот же сдвиг выглядит иначе — компенсируем,
        # иначе фигура при растяжении «убегает» из-под курсора
        shift = _rotate_around(new_rect.center(), centre, self.angle) - new_rect.center()
        self.points = [new_rect.topLeft() + shift, new_rect.bottomRight() + shift]
        self.update()

    def move_by(self, dx: float, dy: float):
        self.points = [QPointF(p.x() + dx, p.y() + dy) for p in self.points]
        self.update()

    # ---------- поворот ----------

    def begin_rotate(self, pos: QPointF) -> None:
        """Запомнить состояние на начало вращения: дальше считаем от него, а не шагами —
        иначе у полигона на длинной протяжке накапливалась бы погрешность."""
        centre = self.centre()
        self._rotate_from = (self.angle, _angle_of(pos, centre),
                             [QPointF(p) for p in self.points], centre)

    def rotate_to(self, pos: QPointF, snap: bool = False) -> None:
        """Повернуть по курсору. snap (Shift) — привязка к шагу SNAP_DEG."""
        if self._rotate_from is None:
            self.begin_rotate(pos)
        angle0, cursor0, points0, centre = self._rotate_from
        delta = _angle_of(pos, centre) - cursor0
        if self.kind == "polygon":
            if snap:
                delta = round(delta / SNAP_DEG) * SNAP_DEG
            self.points = [_rotate_around(p, centre, delta) for p in points0]
        else:
            angle = angle0 + delta
            self.angle = round(angle / SNAP_DEG) * SNAP_DEG if snap else angle
        self.update()

    def end_rotate(self) -> None:
        self._rotate_from = None

    def world_angle(self) -> float:
        """Угол для мировых координат, радианы. Знак обратный экранному: в мире ось z
        смотрит на север, а на экране y — вниз."""
        return -math.radians(self.angle)

    # ---------- правка вершин полигона ----------

    def add_point(self, pos: QPointF):
        """Очередная вершина при построении (клики полигона, траектория лассо)."""
        self.points.append(pos)
        self.update()

    def insert_point(self, after: int, pos: QPointF) -> int:
        """Вставить вершину после `after` (клик по ребру). Возвращает индекс новой."""
        index = after + 1
        self.points.insert(index, pos)
        self.update()
        return index

    def remove_point(self, i: int) -> bool:
        """Убрать вершину (двойной клик). Ниже трёх не опускаемся — иначе не фигура."""
        if self.kind != "polygon" or len(self.points) <= 3 or not 0 <= i < len(self.points):
            return False
        del self.points[i]
        self.update()
        return True

    # ---------- применение ----------

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
        """Сцена -> мировые метры (юг = 0). Поворот НЕ применяется: см. `commit_payload`."""
        return [self._to_world(p) for p in self.points]

    def _to_world(self, p: QPointF) -> tuple[float, float]:
        return p.x() - self._margin, self._world - (p.y() - self._margin)

    def commit_payload(self) -> tuple[str, list[tuple[float, float]], float]:
        """(kind, точки в метрах, угол в радианах) для заливки.

        Повёрнутый прямоугольник отдаём полигоном из четырёх углов: правило попадания
        ячейки у полигона то же (центр внутри), так что заливка совпадает с превью,
        а `core.shapes` не нужно учить ещё одному повороту. Эллипс так не разложить —
        ему угол передаётся как есть."""
        if self.kind == "rect" and self.angle % 360:
            r, centre = self.rect(), self.rect().center()
            corners = [r.topLeft(), r.topRight(), r.bottomRight(), r.bottomLeft()]
            return "polygon", [self._to_world(_rotate_around(p, centre, self.angle))
                               for p in corners], 0.0
        return self.kind, self.world_points(), self.world_angle()

    # ---------- отрисовка ----------

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(255, 255, 255), 2, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)                    # 2 px на экране при любом зуме
        painter.setPen(pen)
        painter.setBrush(QColor(255, 255, 255, 40))
        if self.kind in ("rect", "ellipse"):
            centre = self.rect().center()
            painter.save()
            painter.translate(centre)
            painter.rotate(self.angle)
            painter.translate(-centre)
            if self.kind == "rect":
                painter.drawRect(self.rect())
            else:
                painter.drawEllipse(self.rect())
            painter.restore()
        else:
            poly = QPolygonF(self.points)
            if self.building:                    # ломаная + «резиновая» линия к курсору
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPolyline(poly)
                if self.cursor is not None and self.points:
                    painter.drawLine(self.points[-1], self.cursor)
            else:
                painter.drawPolygon(poly)
        if self.building:                        # пока строим — ни ручек, ни поворота
            return
        for h in self._shape_handles():          # ручки — экранного размера
            painter.save()
            painter.translate(h)
            painter.scale(1.0 / lod, 1.0 / lod)
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.setBrush(QColor(255, 255, 255))
            painter.drawRect(QRectF(-HANDLE_PX / 2, -HANDLE_PX / 2,
                                    HANDLE_PX, HANDLE_PX))
            painter.restore()
        self._paint_rotate_handle(painter, lod)

    def _paint_rotate_handle(self, painter: QPainter, lod: float):
        """Кружок на «стебле» над фигурой — чтобы его не путали с квадратными ручками."""
        knob = self._rotate_handle(lod)
        stalk = QPen(QColor(255, 255, 255), 1)
        stalk.setCosmetic(True)
        painter.setPen(stalk)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawLine(self._top_centre(), knob)
        painter.save()
        painter.translate(knob)
        painter.scale(1.0 / lod, 1.0 / lod)
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        painter.setBrush(QColor(255, 235, 130))  # жёлтый: это не ручка размера
        painter.drawEllipse(QPointF(0, 0), ROTATE_R_PX, ROTATE_R_PX)
        painter.restore()


def _angle_of(pos: QPointF, centre: QPointF) -> float:
    """Направление на точку от центра, градусы (по часовой на экране)."""
    return math.degrees(math.atan2(pos.y() - centre.y(), pos.x() - centre.x()))


def _distance_to_segment_sq(p: QPointF, a: QPointF, b: QPointF) -> float:
    """Квадрат расстояния от точки до отрезка — для попадания курсором по ребру."""
    dx, dy = b.x() - a.x(), b.y() - a.y()
    length_sq = dx * dx + dy * dy
    if length_sq <= 0:
        return (p.x() - a.x()) ** 2 + (p.y() - a.y()) ** 2
    t = max(0.0, min(1.0, ((p.x() - a.x()) * dx + (p.y() - a.y()) * dy) / length_sq))
    return (p.x() - a.x() - t * dx) ** 2 + (p.y() - a.y() - t * dy) ** 2
