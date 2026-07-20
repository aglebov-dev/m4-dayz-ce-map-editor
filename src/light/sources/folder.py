"""Источник «Из файловой системы» — папка сервера DayZ или папка миссии.

Отвечает только за ПОДКЛЮЧЕНИЕ (выбор папки → LocalProvider); дальнейшую настройку
(миссия/файлы/имя/подложка) и сборку проекта делает общий `ConfigurePanel`."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from core.i18n import tr
from light.configure_panel import ConfigurePanel
from light.providers import LocalProvider, ProviderError
from light.sources.base import ProjectSource


class FolderProjectSource(ProjectSource):
    id = "folder"
    title = "src.folder"

    def build_widget(self) -> QWidget:
        widget = QWidget()
        self.widget = widget
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(tr("src.folder_root_label")))
        folder_row = QHBoxLayout()
        self.folder_edit = QLineEdit()
        self.folder_edit.returnPressed.connect(self._connect)
        open_button = QPushButton(tr("src.open_folder"))
        open_button.clicked.connect(self._pick_folder)
        self.connect_button = QPushButton(tr("src.connect"))
        self.connect_button.clicked.connect(self._connect)
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(open_button)
        folder_row.addWidget(self.connect_button)
        layout.addLayout(folder_row)

        self.panel = ConfigurePanel()
        self.panel.ready_changed.connect(self._on_ready)
        layout.addWidget(self.panel, 1)

        self.create_button = QPushButton(tr("src.load_project"))
        self.create_button.setEnabled(False)
        self.create_button.clicked.connect(self._create)
        layout.addWidget(self.create_button)
        return widget

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self.widget, tr("src.folder_dlg"))
        if folder:
            self.folder_edit.setText(folder)
            self._connect()

    def _connect(self) -> None:
        root = self.folder_edit.text().strip()
        if not root:
            return
        try:
            provider = LocalProvider(root)
        except ProviderError as error:
            QMessageBox.warning(self.panel, tr("src.source_err_title"),
                                tr("src.source_err", error=error))
            self.panel.clear()
            return
        self.panel.set_provider(provider, {"kind": "local", "root": root})

    def _on_ready(self, ready: bool) -> None:
        self.create_button.setEnabled(ready)

    def _create(self) -> None:
        project = self.panel.build_project()
        if project is not None:
            self.emit_project(project)
