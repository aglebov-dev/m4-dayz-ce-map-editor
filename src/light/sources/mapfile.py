"""Источник «карта из PBO» — открыть подложку без миссии, просто посмотреть.

Остальные источники дают миссию с `areaflags.map`; здесь её нет вовсе. Пользователь
указывает PBO с тайлами, мы распаковываем пирамиду и собираем проект, у которого есть
только подложка: `files` пуст, поэтому гейтинг сам гасит все инструменты — редактор
работает как просмотрщик карты.

Размер мира брать неоткуда, и он тут не нужен: тайлы режутся из пикселей, а метры задают
лишь привязку — `sat_extract` оценивает её по полотну (см. `estimate_world_size`)."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout, QWidget,
)

from core.i18n import tr
from light import project as P
from light import tiles_unpack
from light.sources.base import ProjectSource


class MapFileProjectSource(ProjectSource):
    """Вкладка: выбрать PBO с тайлами и открыть карту без проекта и миссии."""

    id = "mapfile"
    title = "src.mapfile_tab"

    def build_widget(self) -> QWidget:
        self.widget = QWidget()
        layout = QVBoxLayout(self.widget)
        layout.addWidget(QLabel(tr("src.mapfile_hint")))

        self.pbo_edit = QLineEdit()
        self.pbo_edit.setPlaceholderText(tr("src.mapfile_ph"))
        self.pbo_edit.textChanged.connect(self._on_pbo_changed)
        pick_button = QPushButton(tr("bgp.pick_pbo"))
        pick_button.clicked.connect(self._pick)
        row = QHBoxLayout()
        row.addWidget(self.pbo_edit, 1)
        row.addWidget(pick_button)
        layout.addLayout(row)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("src.mapfile_name_ph"))
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("src.mapfile_name")))
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        self.open_button = QPushButton(tr("src.mapfile_open"))
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open)
        layout.addWidget(self.open_button)
        layout.addStretch(1)
        return self.widget

    def _pick(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self.widget, tr("bgp.pbo_dlg"), "", tr("bgp.pbo_filter"))
        if path:
            self.pbo_edit.setText(path)

    def _on_pbo_changed(self, text: str) -> None:
        path = text.strip()
        self.open_button.setEnabled(os.path.isfile(path))
        if os.path.isfile(path) and not self.name_edit.text().strip():
            self.name_edit.setText(tiles_unpack.world_name_from_pbo(path))

    def _open(self) -> None:
        path = self.pbo_edit.text().strip()
        world = (self.name_edit.text().strip()
                 or tiles_unpack.world_name_from_pbo(path))
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            tiles_unpack.unpack_pbo(path, world, 0, log=lambda _m: None)
        except tiles_unpack.UnpackError as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self.widget, tr("bgp.unpack_fail_title"), str(error))
            return
        finally:
            if QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()
        self.emit_project(create_map_project(path, world))


def create_map_project(pbo_path: str, world: str) -> P.Project:
    """Проект-просмотрщик: ни миссии, ни файлов — одна подложка.

    `provider_cfg` помнит PBO, чтобы «перезагрузить» могло распаковать заново."""
    project = P.Project(
        id=P.new_id(world),
        name=world,
        provider_cfg={"kind": "pbo", "pbo": os.path.abspath(pbo_path)},
        mission_name="",
        files={},
        background=f"tiles:{world}")
    project.save()
    return project
