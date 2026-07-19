"""Подписи зон на карте: номер и площадь у центроида зоны выбранного слоя.
Размер текста не зависит от зума; подпись показывается, только если сама зона на экране
достаточно крупная (иначе мелочь залепила бы карту)."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem

from core.i18n import tr

# зона мельче этого размера на экране (px по большей стороне) — без подписи
MIN_ZONE_PX = 18
# потолок подписей за отрисовку: зон бывают тысячи, читаемы всё равно единицы
MAX_LABELS = 250
# зазор между пилюлями при отборе: подписи не должны касаться друг друга
LABEL_GAP_PX = 3
SELECT_COLOR = QColor(255, 64, 64)       # зона, выбранная в панели «Зоны»


class ZoneLabelsItem(QGraphicsItem):
    """Подписи зон одного слоя. zones — из core.zones.find_zones (ячейки, row 0 = ЮГ)."""

    def __init__(self, zones, cell_size: float, world_size: int, margin: int,
                 color: tuple[int, int, int]):
        super().__init__()
        self._world = world_size
        self._margin = margin
        self._color = QColor(*color)
        self._selected: int | None = None         # индекс зоны в списке панели
        self._items: list[tuple[float, float, float, str]] = []   # x, y, размер_м, текст
        for i, z in enumerate(zones[:MAX_LABELS], 1):
            wx = (z.centroid[0] + 0.5) * cell_size
            wz = (z.centroid[1] + 0.5) * cell_size
            ha = z.cells * cell_size * cell_size / 10_000
            span = max(z.bbox[2] - z.bbox[0] + 1, z.bbox[3] - z.bbox[1] + 1) * cell_size
            text = tr("zones.map_label", i=i, ha=f"{ha:,.0f}".replace(",", " "))
            self._items.append((margin + wx, margin + (world_size - wz), span, text))

    def set_selected(self, index: int | None):
        self._selected = index
        self.update()

    def set_color(self, color: tuple[int, int, int]):
        self._color = QColor(*color)
        self.update()

    def boundingRect(self) -> QRectF:
        s = self._world + 2 * self._margin
        return QRectF(0, 0, s, s)

    @staticmethod
    def _font() -> QFont:
        f = QFont()
        f.setPixelSize(11)
        f.setBold(True)
        return f

    def layout(self, lod: float, world) -> list[tuple[int, float, float]]:
        """Какие подписи рисуются при данном зуме: [(индекс зоны, ширина, высота)].
        Зоны отсортированы по убыванию площади — крупные занимают место первыми,
        мелкие уступают им и всплывают при зуме, когда место освободится."""
        fm = QFontMetricsF(self._font())
        placed: list[QRectF] = []                 # занятые пилюли, экранные px
        out: list[tuple[int, float, float]] = []
        for i, (x, y, span, text) in enumerate(self._items):
            selected = i == self._selected
            if not selected and span * lod < MIN_ZONE_PX:
                continue                          # зона на экране слишком мелкая
            w = fm.horizontalAdvance(text) + 10
            h = fm.height() + 4
            sp = world.map(QPointF(x, y))         # центр подписи на экране
            box = QRectF(sp.x() - w / 2 - LABEL_GAP_PX, sp.y() - h / 2 - LABEL_GAP_PX,
                         w + 2 * LABEL_GAP_PX, h + 2 * LABEL_GAP_PX)
            if not selected and any(box.intersects(p) for p in placed):
                continue                          # место занято более крупной зоной
            placed.append(box)
            out.append((i, w, h))
        return out

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, _widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setFont(self._font())
        for i, w, h in self.layout(lod, painter.worldTransform()):
            x, y, _, text = self._items[i]
            selected = i == self._selected
            painter.save()
            painter.translate(x, y)
            painter.scale(1.0 / lod, 1.0 / lod)   # экранный размер при любом зуме
            pill = QRectF(-w / 2, -h / 2, w, h)
            # заливка тёмная, а не в цвет слоя: подпись лежит поверх заливки СВОЕГО
            # слоя и цветом в цвет с ней слилась бы; принадлежность несёт рамка
            fill = QColor(SELECT_COLOR) if selected else QColor(20, 20, 20)
            fill.setAlpha(230)
            painter.setBrush(fill)
            painter.setPen(QPen(QColor(255, 255, 255) if selected else self._color,
                                2))
            painter.drawRoundedRect(pill, h / 2, h / 2)
            painter.setPen(QColor(255, 255, 255))
            painter.drawText(pill, Qt.AlignmentFlag.AlignCenter, text)
            painter.restore()
