"""Панель «Спавн»: предметы, которые могут заспавниться в выбранном здании."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QLineEdit, QListWidget, QListWidgetItem, \
    QVBoxLayout, QWidget

from core.i18n import tr
from core.types import ItemType


class LootPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.lbl = QLabel(tr("loot.hint"))
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)
        self.edt = QLineEdit()
        self.edt.setPlaceholderText(tr("loot.filter"))
        self.edt.textChanged.connect(self._refill)
        self.lst = QListWidget()
        self.lst.setUniformItemSizes(True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(self.lbl)
        lay.addWidget(self.edt)
        lay.addWidget(self.lst, 1)
        self._items: list[ItemType] = []
        self._bld_name = ""
        self._counts: dict[str, int] | None = None   # режим области: зданий на предмет
        self._region_bld = 0

    def clear(self):
        self._items = []
        self._bld_name = ""
        self._counts = None
        self.lbl.setText(tr("loot.hint"))
        self.lst.clear()

    def show_items(self, building_name: str, items: list[ItemType]):
        self._items = items
        self._bld_name = building_name
        self._counts = None
        self._refill()

    def show_region_items(self, buildings: int, rows: list[tuple]):
        """Сводка по выделенной области: rows = [(ItemType, в скольких зданиях)]."""
        self._items = [t for t, _ in rows]
        self._counts = {t.name: n for t, n in rows}
        self._region_bld = buildings
        self._bld_name = ""
        self._refill()

    def _refill(self):
        self.lst.clear()
        if not self._bld_name and self._counts is None:
            return
        # многочастный запрос: все части должны входить в имя/категорию
        tokens = self.edt.text().strip().lower().split()
        shown = 0
        for t in self._items:
            hay = f"{t.name.lower()} {t.category or ''}"
            if tokens and not all(tok in hay for tok in tokens):
                continue
            text = f"{t.name}   ·  {t.category}  ·  nom {t.nominal} / min {t.min}"
            if self._counts is not None:         # в области: где именно возможен
                text += tr("loot.in_buildings", n=self._counts.get(t.name, 0))
            it = QListWidgetItem(text)
            it.setToolTip(f"{t.name}\nrestock {t.restock}s, lifetime {t.lifetime}s\n"
                          f"{t.source}")
            self.lst.addItem(it)
            shown += 1
        if self._counts is None:
            self.lbl.setText(tr("loot.header", name=self._bld_name,
                                n=shown, total=len(self._items)))
        else:
            self.lbl.setText(tr("loot.header_region", bld=f"{self._region_bld:,}"
                                .replace(",", " "), n=shown, total=len(self._items)))
