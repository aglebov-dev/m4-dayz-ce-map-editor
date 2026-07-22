"""Панель «Items»: список типов CE с поиском и выбором. Выбранные предметы — объединённый
слой зданий на карте, где они могут спавниться.

Выбор — обычным кликом по строке (мульти — Ctrl/Shift); чекбоксов нет. Тумблер «только для
спавна» прячет типы, которые CE не спавнит (nominal 0 или без категории)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from core.types import ItemType
from ui.layers_panel import Switch

MAX_SELECT = 25          # больше выбирать бессмысленно — карта зальётся целиком


class ItemsPanel(QWidget):
    selection_changed = Signal(list)     # имена выбранных предметов

    def __init__(self, parent=None):
        super().__init__(parent)
        self.lbl = QLabel(tr("items.hint"))
        self.lbl.setWordWrap(False)              # одна строка: ничего не прыгает
        self.lbl.setFixedHeight(self.lbl.sizeHint().height())
        self.lbl.setTextFormat(Qt.TextFormat.RichText)

        self.edt = QLineEdit()
        self.edt.setPlaceholderText(tr("items.search"))
        self.edt.textChanged.connect(self._apply_filter)
        self.btn_clear = QPushButton(tr("items.clear"))
        self.btn_clear.clicked.connect(self.clear_selection)
        row = QHBoxLayout()
        row.addWidget(self.edt, 1)
        row.addWidget(self.btn_clear)

        # тумблер: прятать типы, которые не спавнятся (по умолчанию — прячем)
        self.sw_spawnable = Switch((76, 175, 80), self)
        self.sw_spawnable.setChecked(True)
        self.sw_spawnable.setToolTip(tr("items.only_spawnable_tip"))
        self.sw_spawnable.toggled.connect(lambda _on: self._apply_filter(self.edt.text()))
        mode = QHBoxLayout()
        mode.addWidget(self.sw_spawnable)
        mode.addWidget(QLabel(tr("items.only_spawnable")))
        mode.addStretch(1)

        self.lst = QListWidget()
        self.lst.setUniformItemSizes(True)       # виртуализация рисования на 6k строк
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.lst.itemSelectionChanged.connect(self._on_selection_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.lbl)
        lay.addLayout(row)
        lay.addLayout(mode)
        lay.addWidget(self.lst, 1)
        self._names: list[str] = []
        self._spawnable: dict[str, bool] = {}

    # ---------- данные ----------

    def populate(self, types: dict[str, ItemType]):
        self.clear()
        self.lst.blockSignals(True)
        for t in sorted(types.values(), key=lambda t: t.name.lower()):
            spawnable = t.nominal > 0 and t.category is not None
            it = QListWidgetItem(f"{t.name}   ·  {t.category or '—'}")
            it.setData(Qt.ItemDataRole.UserRole, t.name)
            it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)   # без чекбоксов
            if not spawnable:                    # CE не спавнит — серым и не выбирается
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.lst.addItem(it)
            self._names.append(t.name)
            self._spawnable[t.name] = spawnable
        self.lst.blockSignals(False)
        self._apply_filter(self.edt.text())

    def clear(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        self.lst.blockSignals(False)
        self._names = []
        self._spawnable = {}
        self.lbl.setText(tr("items.hint"))

    def clear_selection(self):
        self.lst.blockSignals(True)
        self.lst.clearSelection()
        self.lst.blockSignals(False)
        self.edt.clear()                         # «Очистить всё» чистит и поиск
        self.lbl.setText(tr("items.hint"))
        self.selection_changed.emit([])

    def selected_names(self) -> list[str]:
        return [it.data(Qt.ItemDataRole.UserRole) for it in self.lst.selectedItems()]

    def set_result(self, n_buildings: int):
        names = self.selected_names()
        if names:
            self.lbl.setText(tr("items.header", sel=len(names),
                                n=f"{n_buildings:,}".replace(",", " ")))
        else:
            self.lbl.setText(tr("items.hint"))

    # ---------- события ----------

    def _on_selection_changed(self):
        names = self.selected_names()
        if len(names) > MAX_SELECT:              # лимит: дальше карта зальётся целиком
            self.lst.blockSignals(True)
            for it in self.lst.selectedItems()[MAX_SELECT:]:
                it.setSelected(False)
            self.lst.blockSignals(False)
            names = self.selected_names()
            self.lbl.setText(tr("items.limit", max=MAX_SELECT))
        self.selection_changed.emit(sorted(names))

    def _apply_filter(self, q: str):
        # многочастный запрос: строка подходит, если ВСЕ части входят в текст
        # («vzp ak» найдёт ak_mey_super_vzp)
        tokens = q.strip().lower().split()
        only_spawnable = self.sw_spawnable.isChecked()
        changed = False
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            name = it.data(Qt.ItemDataRole.UserRole)
            hidden = (only_spawnable and not self._spawnable.get(name, True)) or (
                bool(tokens) and not all(t in it.text().lower() for t in tokens))
            if hidden and it.isSelected():       # спрятанное не должно оставаться в выборе
                it.setSelected(False)
                changed = True
            self.lst.setRowHidden(i, hidden)
        if changed:
            self._on_selection_changed()
