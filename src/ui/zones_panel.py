"""Панель «Зоны»: связные области выбранного слоя, клик — переход на карте.
Сверху — свитч видимости слоя (синхронен с панелью «Слои») и цветная подпись слоя."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.zones import Zone
from ui.layers_panel import Switch


class ZonesPanel(QWidget):
    """Сигналы: zone_clicked(x0, z0, x1, z1) — мировой bbox зоны;
    zone_selected(index) — номер зоны в списке (-1 — снято);
    layer_toggle_requested(key, visible) — тогл слоя из шапки;
    labels_toggled(visible) — подписи зон на карте."""

    zone_clicked = Signal(float, float, float, float)
    zone_selected = Signal(int)
    layer_toggle_requested = Signal(str, bool)
    labels_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._key: str | None = None

        self.sw = Switch((120, 120, 120), self)
        self.sw.setToolTip(tr("layers.toggle_tip"))
        self.sw.toggled.connect(self._on_switch)
        self.sw.hide()

        self.lbl = QLabel(tr("zones.hint"))
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)

        head = QHBoxLayout()
        head.addWidget(self.sw)
        head.addWidget(self.lbl, 1)

        self.chk_labels = QCheckBox(tr("zones.labels"))
        self.chk_labels.setToolTip(tr("zones.labels_tip"))
        self.chk_labels.setChecked(True)
        self.chk_labels.toggled.connect(self.labels_toggled)

        self.lst = QListWidget()
        self.lst.itemClicked.connect(self._on_item)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(head)
        lay.addWidget(self.chk_labels)
        lay.addWidget(self.lst, 1)

    def show_zones(self, key: str, layer_name: str, zones: list[Zone], cell_size: float,
                   color: tuple[int, int, int], visible: bool):
        self._key = key
        self.sw.set_color(color)
        self.sw.blockSignals(True)
        self.sw.setChecked(visible)
        self.sw.blockSignals(False)
        self.sw.show()
        total_ha = sum(z.cells for z in zones) * cell_size * cell_size / 10_000
        r, g, b = color
        name_html = f"<b><span style='color: rgb({r},{g},{b});'>{layer_name}</span></b>"
        self.lbl.setText(tr("zones.header", name=name_html, count=len(zones),
                            ha=f"{total_ha:,.1f}".replace(",", " ")))
        self.lst.clear()
        for i, z in enumerate(zones, 1):
            ha = z.cells * cell_size * cell_size / 10_000
            cx = (z.centroid[0] + 0.5) * cell_size
            cz = (z.centroid[1] + 0.5) * cell_size
            it = QListWidgetItem(tr(
                "zones.item", i=i, ha=f"{ha:,.1f}".replace(",", " "),
                x=f"{cx:,.0f}".replace(",", " "), z=f"{cz:,.0f}".replace(",", " ")))
            bbox_world = (z.bbox[0] * cell_size, z.bbox[1] * cell_size,
                          (z.bbox[2] + 1) * cell_size, (z.bbox[3] + 1) * cell_size)
            it.setData(Qt.ItemDataRole.UserRole, bbox_world)
            self.lst.addItem(it)

    @property
    def layer_key(self) -> str | None:
        """Слой, чьи зоны показаны сейчас (None — панель пуста)."""
        return self._key

    def update_layer_state(self, key: str, visible: bool):
        """Синхронизация из панели слоёв (в т.ч. эхо собственного тогла)."""
        if key != self._key or self.sw.isChecked() == visible:
            return
        self.sw.blockSignals(True)
        self.sw.setChecked(visible)
        self.sw.blockSignals(False)

    def clear(self):
        self._key = None
        self.sw.hide()
        self.lbl.setText(tr("zones.hint"))
        self.lst.clear()

    def _on_switch(self, checked: bool):
        if self._key:
            self.layer_toggle_requested.emit(self._key, checked)

    def _on_item(self, it: QListWidgetItem):
        self.zone_selected.emit(self.lst.row(it))
        x0, z0, x1, z1 = it.data(Qt.ItemDataRole.UserRole)
        self.zone_clicked.emit(x0, z0, x1, z1)
