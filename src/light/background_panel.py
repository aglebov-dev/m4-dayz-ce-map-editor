"""Панель ВЫБОРА подложки (спутник) — общая для источников загрузки.

Выбор: нет / уже распакованная пирамида тайлов / картинка с диска. Значение отдаётся
строкой `"" | "tiles:<world>" | "image:<path>"` (как хранит `Project.background`).

Распаковки тут больше нет: она не про проект, а про файлы игры, и живёт во вкладке
«Карта из PBO» (`light.sources.mapfile` + `light.map_import`). Панель только показывает
то, что уже распаковано, — поэтому и мир ей знать незачем."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from core.i18n import tr


class BackgroundPanel(QGroupBox):
    """`value()` — выбранная подложка; `set_world()` оставлен как no-op для совместимости."""

    def __init__(self, parent=None):
        super().__init__(tr("bgp.title"), parent)
        self._image_path = ""

        self.background_combo = QComboBox()
        self.background_combo.currentIndexChanged.connect(self._clear_warning)
        self.image_button = QPushButton(tr("bgp.pick_image"))
        self.image_button.clicked.connect(self._pick_image)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("bgp.image_hint")))
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel(tr("bgp.source")))
        source_row.addWidget(self.background_combo, 1)
        source_row.addWidget(self.image_button)
        layout.addLayout(source_row)
        self._refresh()

    # ---------- публичное ----------

    def value(self) -> str:
        return self.background_combo.currentData() or ""

    def set_value(self, value: str) -> None:
        index = self.background_combo.findData(value or "")
        if index >= 0:
            self.background_combo.setCurrentIndex(index)

    def confirm_or_warn(self, parent) -> bool:
        """True — можно создавать проект. Если подложка НЕ выбрана: подсветить поле и
        спросить подтверждение (добавить подложку позже можно только правкой конфига)."""
        if self.value():
            self._clear_warning()
            return True
        self.background_combo.setStyleSheet("QComboBox { border: 1px solid #e53935; }")
        answer = QMessageBox.warning(
            parent, tr("bgp.none_title"), tr("bgp.none_warn"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def set_world(self, world_name: str = "", world_size: int = 0) -> None:
        """Ничего не делает: панель больше не распаковывает, мир ей не нужен.
        Оставлено, чтобы источники (BI, Folder/SFTP) не переписывать из-за одной строки."""

    def _clear_warning(self, *_args) -> None:
        if self.value():
            self.background_combo.setStyleSheet("")

    # ---------- внутреннее ----------

    def _refresh(self, keep: str = "") -> None:
        from light import tiles_store
        self.background_combo.blockSignals(True)
        self.background_combo.clear()
        self.background_combo.addItem(tr("bgp.none"), "")
        for world in tiles_store.available_worlds():
            self.background_combo.addItem(tr("bgp.tiles_item", world=world), f"tiles:{world}")
        if self._image_path:
            self.background_combo.addItem(
                tr("bgp.image_item", file=os.path.basename(self._image_path)),
                f"image:{self._image_path}")
        index = self.background_combo.findData(keep or "")
        self.background_combo.setCurrentIndex(max(0, index))
        self.background_combo.blockSignals(False)

    def _pick_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, tr("bgp.image_dlg"), "", tr("bgp.image_filter"))
        if path:
            self._image_path = path
            self._refresh(keep=f"image:{path}")



