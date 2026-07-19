"""Панель «Items»: весь список типов CE с поиском и мультивыбором галочками.
Отмеченные предметы — объединённый слой зданий на карте, где они могут спавниться."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, \
    QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from core.i18n import tr
from core.types import ItemType
from ui.layers_panel import Switch

MAX_SELECT = 25          # больше выбирать бессмысленно — карта зальётся целиком


class ItemsPanel(QWidget):
    selection_changed = Signal(list)     # имена отмеченных предметов

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

        # режим одиночного выбора: клик по строке заменяет выбор целиком
        self.sw_single = Switch((33, 150, 243), self)
        self.sw_single.setChecked(True)
        self.sw_single.toggled.connect(self._on_single_toggled)
        mode = QHBoxLayout()
        mode.addWidget(self.sw_single)
        mode.addWidget(QLabel(tr("items.single")))
        mode.addStretch(1)

        self.lst = QListWidget()
        self.lst.setUniformItemSizes(True)   # виртуализация рисования на 6k строк
        self.lst.itemChanged.connect(self._on_item_changed)
        self.lst.itemClicked.connect(self._on_item_clicked)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.lbl)
        lay.addLayout(row)
        lay.addLayout(mode)
        lay.addWidget(self.lst, 1)
        self._names: list[str] = []
        self._checked: set[str] = set()

    # ---------- данные ----------

    def populate(self, types: dict[str, ItemType]):
        self.clear()
        self.lst.blockSignals(True)
        items = sorted(types.values(), key=lambda t: t.name.lower())
        for t in items:
            it = QListWidgetItem(f"{t.name}   ·  {t.category or '—'}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Unchecked)
            it.setData(Qt.ItemDataRole.UserRole, t.name)
            if t.nominal <= 0 or t.category is None:
                it.setFlags(it.flags() & ~Qt.ItemFlag.ItemIsEnabled)   # не спавнится CE
            self.lst.addItem(it)
            self._names.append(t.name)
        self.lst.blockSignals(False)

    def clear(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        self.lst.blockSignals(False)
        self._names = []
        self._checked = set()
        self.lbl.setText(tr("items.hint"))

    def clear_selection(self):
        self.lst.blockSignals(True)
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                it.setCheckState(Qt.CheckState.Unchecked)
        self.lst.blockSignals(False)
        self._checked = set()
        self.edt.clear()                         # «Очистить всё» чистит и поиск
        self.lbl.setText(tr("items.hint"))
        self.selection_changed.emit([])

    def checked_names(self) -> list[str]:
        return sorted(self._checked)

    def set_result(self, n_buildings: int):
        if self._checked:
            self.lbl.setText(tr("items.header",
                                sel=len(self._checked),
                                n=f"{n_buildings:,}".replace(",", " ")))
        else:
            self.lbl.setText(tr("items.hint"))

    # ---------- события ----------

    def _on_item_changed(self, it: QListWidgetItem):
        name = it.data(Qt.ItemDataRole.UserRole)
        if it.checkState() == Qt.CheckState.Checked:
            if self.sw_single.isChecked():           # сингл: заменяем выбор целиком
                self._uncheck_all_except(it)
                self._checked = {name}
                self.selection_changed.emit([name])
                return
            if len(self._checked) >= MAX_SELECT:     # лимит: дальше бессмысленно
                self.lst.blockSignals(True)
                it.setCheckState(Qt.CheckState.Unchecked)
                self.lst.blockSignals(False)
                self.lbl.setText(tr("items.limit", max=MAX_SELECT))
                return
            self._checked.add(name)
        else:
            self._checked.discard(name)
        self.selection_changed.emit(sorted(self._checked))

    def _on_item_clicked(self, it: QListWidgetItem):
        """В сингл-режиме клик по строке выбирает предмет (повторный — снимает)."""
        if not self.sw_single.isChecked() or not it.flags() & Qt.ItemFlag.ItemIsEnabled:
            return
        want = (Qt.CheckState.Unchecked if it.checkState() == Qt.CheckState.Checked
                else Qt.CheckState.Checked)
        it.setCheckState(want)                       # дальше отработает _on_item_changed

    def _on_single_toggled(self, single: bool):
        """Мульти -> сингл с несколькими отмеченными: выбор сбрасывается."""
        if single and len(self._checked) > 1:
            self.clear_selection()

    def _uncheck_all_except(self, keep: QListWidgetItem):
        self.lst.blockSignals(True)
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it is not keep and it.checkState() == Qt.CheckState.Checked:
                it.setCheckState(Qt.CheckState.Unchecked)
        self.lst.blockSignals(False)

    def _apply_filter(self, q: str):
        # многочастный запрос: строка подходит, если ВСЕ части входят в текст
        # («vzp ak» найдёт ak_mey_super_vzp)
        tokens = q.strip().lower().split()
        for i in range(self.lst.count()):
            text = self.lst.item(i).text().lower()
            self.lst.setRowHidden(i, bool(tokens)
                                  and not all(t in text for t in tokens))
