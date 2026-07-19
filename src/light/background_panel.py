"""Панель выбора подложки (спутник) — общая для источников загрузки.

Выбор: нет / готовая пирамида тайлов мира / картинка с диска; плюс распаковка тайлов из
файлов игры. Значение отдаётся строкой `"" | "tiles:<world>" | "image:<path>"` (как хранит
`Project.background`). Переиспользуется `ConfigurePanel` (Folder/SFTP) и BI-источником —
разница только в том, откуда берётся мир для распаковки (`set_world`)."""
from __future__ import annotations

import os

from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout,
)

from core.i18n import tr


class BackgroundPanel(QGroupBox):
    """`value()` — выбранная подложка; `set_world(name, size)` — мир для распаковки тайлов."""

    def __init__(self, parent=None):
        super().__init__(tr("bgp.title"), parent)
        self._image_path = ""
        self._world_name = ""
        self._world_size = 0

        self.background_combo = QComboBox()
        self.background_combo.currentIndexChanged.connect(self._clear_warning)
        self.image_button = QPushButton(tr("bgp.pick_image"))
        self.image_button.clicked.connect(self._pick_image)
        self.game_edit = QLineEdit()
        self.game_edit.setPlaceholderText(tr("bgp.game_ph"))
        self.game_button = QPushButton(tr("src.open_folder"))
        self.game_button.clicked.connect(self._pick_game)
        self.unpack_button = QPushButton(tr("bgp.unpack"))
        self.unpack_button.clicked.connect(self._unpack)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("bgp.image_hint")))
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel(tr("bgp.source")))
        source_row.addWidget(self.background_combo, 1)
        source_row.addWidget(self.image_button)
        layout.addLayout(source_row)
        layout.addWidget(QLabel(tr("bgp.unpack_hint")))
        unpack_row = QHBoxLayout()
        unpack_row.addWidget(self.game_edit, 1)
        unpack_row.addWidget(self.game_button)
        unpack_row.addWidget(self.unpack_button)
        layout.addLayout(unpack_row)
        self._refresh()

    # ---------- публичное ----------

    def value(self) -> str:
        return self.background_combo.currentData() or ""

    def set_value(self, value: str) -> None:
        index = self.background_combo.findData(value or "")
        if index >= 0:
            self.background_combo.setCurrentIndex(index)

    def set_world(self, world_name: str, world_size: int) -> None:
        """Мир (имя + метры) — нужен только для распаковки тайлов из игры."""
        self._world_name = world_name or ""
        self._world_size = int(world_size or 0)

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

    def _pick_game(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("bgp.game_dlg"))
        if folder:
            self.game_edit.setText(folder)

    def _unpack(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        from light import tiles_unpack
        if not self._world_name or not self._world_size:
            QMessageBox.information(self, tr("bgp.unpack_title"), tr("bgp.need_map"))
            return
        if not tiles_unpack.available():
            QMessageBox.warning(self, tr("bgp.unpack_title"),
                                tr("bgp.need_dotnet", script=tiles_unpack.script_path()))
            return
        game = self.game_edit.text().strip()
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            tiles_unpack.unpack(game, self._world_name, self._world_size)
        except tiles_unpack.UnpackError as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, tr("bgp.unpack_fail_title"), str(error))
            return
        QApplication.restoreOverrideCursor()
        self._refresh(keep=f"tiles:{self._world_name}")
        QMessageBox.information(self, tr("bgp.unpack_title"), tr(
            "bgp.unpack_done", world=self._world_name, size=self._world_size))
