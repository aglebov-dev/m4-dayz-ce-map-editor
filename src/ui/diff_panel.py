"""Панель «Дифф»: сравнение текущей карты с другим areaflags.map.
Клик по строке флага — оверлей различий на карте (зелёное появилось, красное пропало)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from core.diff import MapDiff
from core.i18n import tr
from ui.overlays import DIFF_ADDED, DIFF_REMOVED


class DiffPanel(QWidget):
    """Сигналы: snapshot_requested() — сравнить со снапшотом проекта;
    load_requested() — выбрать другой areaflags.map; flag_clicked(key) — дифф флага
    на карте; clear_requested()."""

    snapshot_requested = Signal()
    load_requested = Signal()
    flag_clicked = Signal(str)
    clear_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.btn_snapshot = QPushButton(tr("diff.snapshot"))
        self.btn_snapshot.clicked.connect(self.snapshot_requested)
        self.btn_snapshot.setEnabled(False)
        self.btn_load = QPushButton(tr("diff.load"))
        self.btn_load.clicked.connect(self.load_requested)
        self.btn_clear = QPushButton(tr("diff.clear"))
        self.btn_clear.clicked.connect(self.clear_requested)
        self.btn_clear.setEnabled(False)
        top = QHBoxLayout()
        top.addWidget(self.btn_snapshot, 1)
        top.addWidget(self.btn_clear, 1)
        second = QHBoxLayout()
        second.addWidget(self.btn_load, 1)
        buttons = QVBoxLayout()
        buttons.setSpacing(4)
        buttons.addLayout(top)
        buttons.addLayout(second)

        self.lbl = QLabel(tr("diff.hint"))
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)

        self.legend = QLabel()
        self.legend.setWordWrap(True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.legend.setText(tr(
            "diff.legend",
            add=_swatch(DIFF_ADDED), rem=_swatch(DIFF_REMOVED)))
        self.legend.hide()

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(
            [tr("diff.col_flag"), tr("diff.col_added"), tr("diff.col_removed")])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.tbl.setSortingEnabled(True)
        self.tbl.itemClicked.connect(self._on_item)
        h = self.tbl.horizontalHeader()
        h.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        h.setStretchLastSection(False)
        self.tbl.setColumnWidth(0, 150)
        self.tbl.setColumnWidth(1, 90)
        self.tbl.setColumnWidth(2, 90)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addLayout(buttons)
        lay.addWidget(self.lbl)
        lay.addWidget(self.legend)
        lay.addWidget(self.tbl, 1)

    def set_snapshot_available(self, available: bool):
        """Кнопка «Со снапшотом» активна только при наличии снапшота у проекта."""
        self.btn_snapshot.setEnabled(available)

    def clear(self):
        self.lbl.setText(tr("diff.hint"))
        self.tbl.setRowCount(0)
        self.legend.hide()
        self.btn_clear.setEnabled(False)

    def show_error(self, text: str):
        self.tbl.setRowCount(0)
        self.legend.hide()
        self.btn_clear.setEnabled(False)
        self.lbl.setText(f"<span style='color:#c62828;'>{text}</span>")

    def show_diff(self, d: MapDiff, source: str):
        """d — из core.diff.diff_maps; source — откуда взят второй срез."""
        self.btn_clear.setEnabled(True)
        self.legend.show()
        ha = d.changed_cells * d.cell_size * d.cell_size / 10_000
        self.lbl.setText(tr("diff.header", src=source, cells=_num(d.changed_cells),
                            pct=f"{d.pct:.2f}", ha=_num(ha, 1)))
        rows = [f for f in d.flags if f.changed or f.only_in]
        rows.sort(key=lambda f: f.changed, reverse=True)
        self.tbl.setSortingEnabled(False)
        self.tbl.setRowCount(len(rows))
        for r, f in enumerate(rows):
            name = QTableWidgetItem(f.name)
            name.setData(Qt.ItemDataRole.UserRole, f.key)
            if f.only_in:
                name.setText(f"{f.name}  ({tr('diff.only_a') if f.only_in == 'a' else tr('diff.only_b')})")
            self.tbl.setItem(r, 0, name)
            self.tbl.setItem(r, 1, _NumItem(f.added, _num(f.added)))
            self.tbl.setItem(r, 2, _NumItem(f.removed, _num(f.removed)))
        self.tbl.setSortingEnabled(True)
        if not rows:
            self.lbl.setText(tr("diff.identical", src=source))

    def _on_item(self, it: QTableWidgetItem):
        key = self.tbl.item(it.row(), 0).data(Qt.ItemDataRole.UserRole)
        if key:
            self.flag_clicked.emit(key)


class _NumItem(QTableWidgetItem):
    """Сортировка по числу, а не по тексту."""

    def __init__(self, value: float, text: str):
        super().__init__(text)
        self.value = float(value)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight
                              | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other):
        if isinstance(other, _NumItem):
            return self.value < other.value
        return super().__lt__(other)


def _num(v: float, dec: int = 0) -> str:
    return f"{v:,.{dec}f}".replace(",", " ")


def _swatch(rgb: tuple[int, int, int]) -> str:
    return f"<span style='color: rgb{rgb};'>■</span>"
