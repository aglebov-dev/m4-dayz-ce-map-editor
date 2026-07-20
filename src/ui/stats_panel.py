"""Панель «Статистика»: площади флагов по всей карте или по выделенной области.
Клик по строке флага — то же, что клик по слою в панели «Слои» (зоны + подписи)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from core.i18n import tr
from core.stats import MapStats
from ui.layers_panel import Switch


class StatsPanel(QWidget):
    """Сигналы: select_toggled(on) — включён режим выделения области (ЛКМ тянет рамку);
    flag_clicked(key) — строка флага. Статистика: по всей карте, а при активном выделении —
    по нему."""

    select_toggled = Signal(bool)
    flag_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.select_switch = Switch((80, 150, 240))
        self.select_switch.setToolTip(tr("toolbar.select_region_tip"))
        self.select_switch.toggled.connect(self.select_toggled)

        top = QHBoxLayout()
        top.addWidget(self.select_switch)
        top.addWidget(QLabel(tr("toolbar.select_region")))
        top.addStretch(1)

        self.lbl = QLabel(tr("stats.hint"))
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)

        self.tbl = QTableWidget(0, 4)
        self.tbl.setHorizontalHeaderLabels([
            tr("stats.col_flag"), tr("stats.col_cells"),
            tr("stats.col_km2"), tr("stats.col_pct")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.itemClicked.connect(self._on_item)
        h = self.tbl.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c in (1, 2, 3):
            h.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(top)
        lay.addWidget(self.lbl)
        lay.addWidget(self.tbl, 1)

    def set_select(self, on: bool):
        """Синхронизировать тогл без эмита сигнала (напр. когда выделение снял другой инструмент)."""
        self.select_switch.blockSignals(True)
        self.select_switch.setChecked(on)
        self.select_switch.blockSignals(False)

    def clear(self):
        self.lbl.setText(tr("stats.hint"))
        self.tbl.setRowCount(0)
        self.set_select(False)

    def show_stats(self, st: MapStats, colors: dict[str, tuple[int, int, int]],
                   region_world=None):
        """st — из core.stats.map_stats; colors — key -> RGB (из панели слоёв)."""
        if region_world is None:
            head = tr("stats.header_map", km2=_num(st.area_km2, 2),
                      cells=_num(st.cells), bld=_num(st.buildings))
        else:
            x0, z0, x1, z1 = region_world
            head = tr("stats.header_region", km2=_num(st.area_km2, 2),
                      cells=_num(st.cells), bld=_num(st.buildings),
                      x0=_num(x0), z0=_num(z0), x1=_num(x1), z1=_num(z1))
        self.lbl.setText(head)

        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(len(st.flags))
        for r, f in enumerate(st.flags):
            name = QTableWidgetItem(f.name)
            name.setData(Qt.ItemDataRole.UserRole, f.key)
            name.setIcon(_chip(colors.get(f.key, (140, 140, 140))))
            name.setToolTip(tr("stats.row_tip", flag=f.key))
            self.tbl.setItem(r, 0, name)
            self.tbl.setItem(r, 1, _NumItem(f.cells, _num(f.cells)))
            self.tbl.setItem(r, 2, _NumItem(f.area_km2, _num(f.area_km2, 2)))
            self.tbl.setItem(r, 3, _NumItem(f.pct, f"{f.pct:.2f} %"))
        self.tbl.setSortingEnabled(True)

    def _on_item(self, it: QTableWidgetItem):
        key = self.tbl.item(it.row(), 0).data(Qt.ItemDataRole.UserRole)
        if key:
            self.flag_clicked.emit(key)


def _num(v: float, dec: int = 0) -> str:
    return f"{v:,.{dec}f}".replace(",", " ")


class _NumItem(QTableWidgetItem):
    """Ячейка, которая сортируется по ЧИСЛУ, а не по тексту («9» > «10» как строки)."""

    def __init__(self, value: float, text: str):
        super().__init__(text)
        self.value = float(value)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self.value < other.value
        return super().__lt__(other)


def _chip(rgb: tuple[int, int, int]) -> QPixmap:
    pm = QPixmap(12, 12)
    pm.fill(QColor(*rgb))
    return pm
