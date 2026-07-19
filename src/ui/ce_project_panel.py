"""Панель «Проект BI»: импорт проекта CE Tool — воду/сушу и сравнение слоёв
проекта с боевым areaflags. Только чтение (экспорт обратно — отдельное решение)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton,
    QVBoxLayout, QWidget,
)

from core.i18n import tr


class CeProjectPanel(QWidget):
    """Сигналы: load_requested(); water_toggled(bool);
    layer_clicked(name) — наложить слой проекта для сравнения; clear_overlay()."""

    load_requested = Signal()
    water_toggled = Signal(bool)
    layer_clicked = Signal(str)
    clear_overlay = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.btn_load = QPushButton(tr("ce.load"))
        self.btn_load.clicked.connect(self.load_requested)

        self.lbl = QLabel(tr("ce.hint"))
        self.lbl.setWordWrap(True)
        self.lbl.setTextFormat(Qt.TextFormat.RichText)

        self.chk_water = QCheckBox(tr("ce.water"))
        self.chk_water.setToolTip(tr("ce.water_tip"))
        self.chk_water.toggled.connect(self.water_toggled)
        self.chk_water.setEnabled(False)

        self.lst = QLabel(tr("ce.layers_hint"))
        self.lst.setWordWrap(True)
        self.layers = QListWidget()
        self.layers.itemClicked.connect(self._on_layer)

        self.btn_clear = QPushButton(tr("ce.clear"))
        self.btn_clear.clicked.connect(self.clear_overlay)
        self.btn_clear.setEnabled(False)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        top = QHBoxLayout()
        top.addWidget(self.btn_load, 1)
        top.addWidget(self.btn_clear)
        lay.addLayout(top)
        lay.addWidget(self.lbl)
        lay.addWidget(self.chk_water)
        lay.addWidget(self.lst)
        lay.addWidget(self.layers, 1)

    def clear(self):
        self.lbl.setText(tr("ce.hint"))
        self.chk_water.setChecked(False)
        self.chk_water.setEnabled(False)
        self.layers.clear()
        self.btn_clear.setEnabled(False)

    def show_error(self, text: str):
        self.clear()
        self.lbl.setText(f"<span style='color:#c62828;'>{text}</span>")

    def show_project(self, name: str, layer_names: list[str], has_water: bool):
        self.lbl.setText(tr("ce.loaded", name=name, n=len(layer_names)))
        self.chk_water.setEnabled(has_water)
        self.layers.clear()
        for n in layer_names:
            self.layers.addItem(QListWidgetItem(n))

    def set_overlay_active(self, active: bool):
        self.btn_clear.setEnabled(active)

    def _on_layer(self, it: QListWidgetItem):
        self.layer_clicked.emit(it.text())
