"""Источник «Импорт проекта BI» — проект CE Tool (Bohemia): XML + TGA-слои.

Папка проекта CE Tool конвертируется в полноценный редактируемый проект (areaflags из
TGA-слоёв, см. `light.bi_import`). Работает вкладка «Карта»; объекты/спавн/территории у
такого проекта нет (данных нет)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from core.i18n import tr
from light import bi_import
from light.background_panel import BackgroundPanel
from light.sources.base import ProjectSource


class BiProjectSource(ProjectSource):
    id = "bi"
    title = "src.bi"

    def build_widget(self) -> QWidget:
        self._summary = None

        widget = QWidget()
        self.widget = widget
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(tr("src.bi_folder_label")))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.returnPressed.connect(self._read)
        open_button = QPushButton(tr("src.open_folder"))
        open_button.clicked.connect(self._pick_folder)
        read_button = QPushButton(tr("src.check"))
        read_button.clicked.connect(self._read)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(open_button)
        folder_row.addWidget(read_button)
        layout.addLayout(folder_row)

        self.info_label = QLabel("")
        self.info_label.setWordWrap(True)
        self.info_label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self.info_label)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("src.name_label")))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("src.name_ph"))
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        self.background_panel = BackgroundPanel()
        layout.addWidget(self.background_panel)

        layout.addStretch(1)

        self.import_button = QPushButton(tr("src.import_project"))
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import)
        layout.addWidget(self.import_button)
        return widget

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.widget, tr("src.bi_folder_dlg"))
        if folder:
            self.folder_edit.setText(folder)
            self._read()

    def _read(self) -> None:
        folder = self.folder_edit.text().strip()
        self._summary = None
        self.import_button.setEnabled(False)
        if not folder:
            return
        try:
            summary = bi_import.read_summary(folder)
        except (ValueError, OSError) as error:
            self.info_label.setText(
                f"<span style='color:#c62828'>{tr('src.bi_not_ce', error=error)}</span>")
            return
        self._summary = summary
        self.info_label.setText(tr(
            "src.bi_summary", grid=summary.layer_size, world=summary.world_size,
            u=len(summary.usages), v=len(summary.values), n=len(summary.layers)))
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.basename(os.path.normpath(folder)) or "BI_project")
        world = os.path.basename(os.path.normpath(folder)).lower()
        self.background_panel.set_world(world, summary.world_size)
        self.import_button.setEnabled(True)

    def _import(self) -> None:
        if not self.background_panel.confirm_or_warn(self.widget):
            return
        folder = self.folder_edit.text().strip()
        name = self.name_edit.text().strip() or "BI_project"
        try:
            project = bi_import.create_project(
                folder, name, background=self.background_panel.value())
        except Exception as error:
            QMessageBox.critical(self.widget, tr("src.bi_import_err_title"),
                                 tr("src.bi_import_err", error=error))
            return
        self.emit_project(project)
