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

from light import bi_import
from light.sources.base import ProjectSource


class BiProjectSource(ProjectSource):
    id = "bi"
    title = "Импорт проекта BI"

    def build_widget(self) -> QWidget:
        self._summary = None

        widget = QWidget()
        self.widget = widget                         # родитель для диалогов (source — QObject)
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel("Папка проекта CE Tool (с XML-проектом и папкой layers):"))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.returnPressed.connect(self._read)
        open_button = QPushButton("Открыть папку")
        open_button.clicked.connect(self._pick_folder)
        read_button = QPushButton("Проверить")
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
        name_row.addWidget(QLabel("Имя проекта:"))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Имя проекта")
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        layout.addStretch(1)

        self.import_button = QPushButton("Импортировать проект")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self._import)
        layout.addWidget(self.import_button)
        return widget

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.widget, "Папка проекта CE Tool")
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
            self.info_label.setText(f"<span style='color:#c62828'>Не проект CE Tool: "
                                    f"{error}</span>")
            return
        self._summary = summary
        self.info_label.setText(
            f"Сетка {summary.layer_size}×{summary.layer_size}, мир {summary.world_size} м · "
            f"usage: {len(summary.usages)} · value: {len(summary.values)} · "
            f"слоёв: {len(summary.layers)}")
        if not self.name_edit.text().strip():
            self.name_edit.setText(os.path.basename(os.path.normpath(folder)) or "BI_project")
        self.import_button.setEnabled(True)

    def _import(self) -> None:
        folder = self.folder_edit.text().strip()
        name = self.name_edit.text().strip() or "BI_project"
        try:
            project = bi_import.create_project(folder, name)
        except Exception as error:
            QMessageBox.critical(self.widget, "Импорт BI",
                                 f"Не удалось импортировать: {error}")
            return
        self.emit_project(project)
