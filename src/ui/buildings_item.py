"""Слои зданий: точки на большом зуме (BuildingsItem, по слою на фильтр) и общий
агрегированный слой кластеров (ClustersItem): якорь — центроид зданий области,
чипы видимых слоёв в ряд у якоря — сопоставимо и без наслоения."""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

CLUSTER_LOD = 0.22       # ниже этого масштаба — кластеры, выше — точки
MIN_CLUSTER_GAP_PX = 64  # минимальный шаг кружков на экране (иначе сливаются)
SELECT_COLOR = QColor(255, 64, 64)               # выделенное здание/кластер
# режим per-layer (v1): каждый слой рисует свои кружки; корзины по уровням
BUCKET_LEVELS = (512.0, 1024.0, 2048.0, 4096.0)


class BuildingsItem(QGraphicsItem):
    """Точки одного слоя зданий. В режиме кластеров молчит (рисует ClustersItem),
    кроме per_layer_clusters=True — тогда рисует СВОИ кружки (v1, «как было»)."""

    def __init__(self, x: np.ndarray, z: np.ndarray, world_size: int, margin: int,
                 color: tuple[int, int, int], per_layer_clusters: bool = False):
        super().__init__()
        self._color = QColor(*color)
        self._world = world_size
        self._margin = margin
        sx = margin + x
        sy = margin + (world_size - z)
        self._points = QPolygonF([QPointF(float(a), float(b)) for a, b in zip(sx, sy)])
        self._sx, self._sy = sx, sy
        self._selected: int | None = None        # локальный индекс выделенного инстанса
        # v1-кластеры слоя: центроиды корзин по уровням + принадлежность инстансов
        self._levels: dict[float, list[tuple[float, float, int]]] = {}
        self._member: dict[float, np.ndarray] = {}
        if per_layer_clusters:
            for bucket in BUCKET_LEVELS:
                bx = (x // bucket).astype(np.int64)
                bz = (z // bucket).astype(np.int64)
                clusters: list[tuple[float, float, int]] = []
                member = np.zeros(len(x), dtype=np.int32)
                order = np.lexsort((bz, bx))
                if len(order):
                    key = bx[order] << 32 | bz[order]
                    splits = np.flatnonzero(np.diff(key)) + 1
                    for ci, idx in enumerate(np.split(order, splits)):
                        member[idx] = ci
                        clusters.append((float(sx[idx].mean()), float(sy[idx].mean()),
                                         int(len(idx))))
                self._levels[bucket] = clusters
                self._member[bucket] = member

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
        if lod < CLUSTER_LOD:
            if self._levels:                     # v1: кружки этого слоя (per-layer)
                self._paint_own_clusters(painter, lod)
            return                               # иначе на отдалении рисует ClustersItem
        # чем ближе зум, тем крупнее точки — чтобы кликом попадать
        size = 4 if lod < 0.6 else 6 if lod < 1.0 else 9
        pen = QPen(self._color, size)
        pen.setCosmetic(True)                    # размер в px экрана при любом зуме
        painter.setPen(pen)
        painter.drawPoints(self._points)
        if self._selected is not None:           # выделение: сама отметка здания
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

    def _paint_own_clusters(self, painter: QPainter, lod: float):
        """v1 («как было»): кружки слоя в центроидах его корзин, в цвете слоя."""
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bucket = next((b for b in BUCKET_LEVELS if b * lod >= MIN_CLUSTER_GAP_PX),
                      BUCKET_LEVELS[-1])
        sel_cluster = (int(self._member[bucket][self._selected])
                       if self._selected is not None else -1)
        font = QFont()
        font.setPixelSize(11)
        fill = QColor(self._color)
        fill.setAlpha(200)
        for ci, (cx, cy, n) in enumerate(self._levels[bucket]):
            r = 9.0 + min(14.0, n ** 0.5)        # экранные px
            painter.save()
            painter.translate(cx, cy)
            painter.scale(1.0 / lod, 1.0 / lod)
            painter.setPen(QPen(QColor(255, 255, 255), 3 if ci == sel_cluster else 1))
            painter.setBrush(fill)
            painter.drawEllipse(QPointF(0, 0), r, r)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRectF(-r, -r, 2 * r, 2 * r),
                             Qt.AlignmentFlag.AlignCenter, str(n))
            painter.restore()


CLUSTER_COLOR = QColor(70, 130, 180)             # нейтральный: «здесь есть здания»
CLUSTER_RADII = (192.0, 384.0, 768.0, 1536.0)    # метры слияния, от мелкого к крупному


def _greedy_merge(x: np.ndarray, z: np.ndarray, w: np.ndarray, r: float):
    """Жадное слияние точек ближе r: (cx, cz, count, assigned). Центроид взвешенный."""
    n = len(x)
    assigned = np.full(n, -1, dtype=np.int32)
    grid: dict[tuple[int, int], list[int]] = {}
    gx = (x // r).astype(np.int64)
    gz = (z // r).astype(np.int64)
    for i in range(n):
        grid.setdefault((int(gx[i]), int(gz[i])), []).append(i)
    out_x: list[float] = []
    out_z: list[float] = []
    out_w: list[int] = []
    r2 = r * r
    for i in np.argsort(-w):                     # крупные сначала — стабильные центры
        if assigned[i] >= 0:
            continue
        ci = len(out_x)
        members = []
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for j in grid.get((int(gx[i]) + dx, int(gz[i]) + dz), ()):
                    if assigned[j] < 0 and (x[j] - x[i]) ** 2 + (z[j] - z[i]) ** 2 <= r2:
                        assigned[j] = ci
                        members.append(j)
        m = np.array(members)
        ww = w[m]
        out_x.append(float((x[m] * ww).sum() / ww.sum()))
        out_z.append(float((z[m] * ww).sum() / ww.sum()))
        out_w.append(int(ww.sum()))
    return (np.array(out_x), np.array(out_z),
            np.array(out_w, dtype=np.int64), assigned)


class ClustersItem(QGraphicsItem):
    """Иерархические кластеры зданий (объединение видимых слоёв, без дублей):
    один нейтральный кружок «здесь N зданий»; при зуме распадается, когда
    кружкам хватает места на экране."""

    def __init__(self, world_size: int, margin: int):
        super().__init__()
        self._world = world_size
        self._margin = margin
        self._levels: list[tuple] = []           # [(cx, cz, count, point->cluster)]
        self._selected: int | None = None        # индекс точки в наборе set_data

    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)

    def set_data(self, x: np.ndarray, z: np.ndarray, selected: int | None):
        """x/z — уникальные здания видимых слоёв; selected — индекс в этом наборе."""
        self._selected = selected
        self._levels = []
        if not len(x):
            self.update()
            return
        cx, cz = x.astype(np.float64), z.astype(np.float64)
        w = np.ones(len(x), dtype=np.int64)
        pt_map = np.arange(len(x), dtype=np.int32)   # точка -> кластер уровня
        for r in CLUSTER_RADII:
            cx, cz, w, assigned = _greedy_merge(cx, cz, w, r)
            pt_map = assigned[pt_map]
            self._levels.append((cx, cz, w, pt_map.copy()))
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        if lod >= CLUSTER_LOD or not self._levels:
            return                               # на приближении точки рисуют слои
        # уровень: минимальный радиус слияния, при котором кружки не толкаются
        need_m = MIN_CLUSTER_GAP_PX / lod
        li = next((k for k, r in enumerate(CLUSTER_RADII) if r >= need_m),
                  len(CLUSTER_RADII) - 1)
        cx, cz, w, pt_map = self._levels[li]
        sel_cluster = int(pt_map[self._selected]) if self._selected is not None else -1
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont()
        font.setPixelSize(11)
        fill = QColor(CLUSTER_COLOR)
        fill.setAlpha(215)
        for k in range(len(cx)):
            ax = self._margin + cx[k]
            ay = self._margin + (self._world - cz[k])
            r = 10.0 + min(16.0, float(w[k]) ** 0.5)     # экранные px
            painter.save()
            painter.translate(ax, ay)
            painter.scale(1.0 / lod, 1.0 / lod)  # экранный размер независимо от зума
            painter.setPen(QPen(QColor(255, 255, 255), 3 if k == sel_cluster else 1))
            painter.setBrush(fill)
            painter.drawEllipse(QPointF(0, 0), r, r)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(QRectF(-r, -r, 2 * r, 2 * r),
                             Qt.AlignmentFlag.AlignCenter, str(int(w[k])))
            painter.restore()
