"""Источник «карта из PBO» — распаковать подложку и здания, а затем открыть карту.

Сюда переехала вся распаковка: и модовая, и ванильная. Панель проекта теперь только
ВЫБИРАЕТ уже готовую пирамиду, потому что распаковка — операция про файлы игры, а не про
миссию (см. `light.map_import`).

Два раздельных действия. «Распаковать» читает PBO и кладёт тайлы с датасетом зданий в
appdata, отчитываясь, что именно получилось. «Открыть» собирает проект-просмотрщик по уже
распакованной пирамиде — им же открывается то, что распаковали в прошлый раз."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from light import map_import, map_scan, project as P, tiles_store, tiles_unpack
from light.sources.base import ProjectSource


class MapFileProjectSource(ProjectSource):
    """Вкладка: найти PBO с тайлами, распаковать и открыть карту без миссии."""

    id = "mapfile"
    title = "src.mapfile_tab"

    def build_widget(self) -> QWidget:
        self.widget = QWidget()
        layout = QVBoxLayout(self.widget)
        hint = QLabel(tr("src.mapfile_hint"))
        hint.setWordWrap(True)                   # подсказка длинная, в одну строку не влезает
        layout.addWidget(hint)

        self.folder_edit = QLineEdit()
        self.folder_edit.setPlaceholderText(tr("src.mapfile_folder_ph"))
        folder_button = QPushButton(tr("src.open_folder"))
        folder_button.clicked.connect(self._pick_folder)
        scan_button = QPushButton(tr("src.mapfile_scan"))
        scan_button.clicked.connect(self._scan)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_edit, 1)
        folder_row.addWidget(folder_button)
        folder_row.addWidget(scan_button)
        layout.addLayout(folder_row)

        self.pbo_combo = QComboBox()
        self.pbo_combo.setEditable(False)
        self.pbo_combo.currentIndexChanged.connect(self._on_pbo_selected)
        pick_button = QPushButton(tr("bgp.pick_pbo"))
        pick_button.clicked.connect(self._pick_pbo)
        pbo_row = QHBoxLayout()
        pbo_row.addWidget(QLabel(tr("src.mapfile_pbo")))
        pbo_row.addWidget(self.pbo_combo, 1)
        pbo_row.addWidget(pick_button)
        layout.addLayout(pbo_row)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(tr("src.mapfile_name_ph"))
        self.name_edit.textChanged.connect(self._sync_buttons)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(tr("src.mapfile_name")))
        name_row.addWidget(self.name_edit, 1)
        layout.addLayout(name_row)

        self.unpack_button = QPushButton(tr("src.mapfile_unpack"))
        self.unpack_button.clicked.connect(self._unpack)
        self.open_button = QPushButton(tr("src.mapfile_open"))
        self.open_button.clicked.connect(self._open)
        button_row = QHBoxLayout()
        button_row.addWidget(self.unpack_button)
        button_row.addWidget(self.open_button)
        layout.addLayout(button_row)

        self.status_label = QLabel(tr("src.mapfile_ready"))
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        layout.addStretch(1)
        self._fill_unpacked()
        self._sync_buttons()
        return self.widget

    # ---------- выбор источника ----------

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self.widget, tr("src.mapfile_folder_dlg"))
        if folder:
            self.folder_edit.setText(folder)
            self._scan()

    def _scan(self) -> None:
        """Найти в папке и тайлы, и файлы миссии — по содержимому, не по имени.

        Читаются только заголовки архивов, поэтому папка мода на 12 ГиБ просматривается за
        доли секунды. Вложенные @Мод/Addons тоже обходим: можно указать корень воркшопа.

        Про миссию сообщаем отдельной строкой: у большинства модов её в архивах нет вовсе
        (экономику держит владелец сервера), а у DeerIsle лежит целиком в `ce.pbo`."""
        folder = self.folder_edit.text().strip()
        if not os.path.isdir(folder):
            self.status_label.setText(tr("src.mapfile_no_folder"))
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            findings = map_scan.scan_folder(folder)
        finally:
            QApplication.restoreOverrideCursor()
        tiles = map_scan.tile_findings(findings)
        self.pbo_combo.clear()
        for finding in tiles:
            # у модов архив почти всегда зовётся data.pbo — различать их можно только по
            # миру из префикса и по папке, откуда взят
            self.pbo_combo.addItem(
                tr("src.mapfile_tiles_item", world=finding.world, n=finding.tiles,
                   source=finding.source), finding.path)
        self._fill_unpacked(keep_paths=True)

        lines = [tr("src.mapfile_found", n=len(tiles)) if tiles else tr("src.mapfile_none")]
        mission = [f for f in map_scan.mission_findings(findings)
                   if f.has_areaflags or len(f.mission) > 2]   # одиночный xml — шум
        if mission:
            for finding in mission[:3]:
                lines.append(tr("src.mapfile_mission", file=finding.name,
                                source=finding.source, n=len(finding.mission),
                                files=", ".join(finding.mission[:4])))
        else:
            lines.append(tr("src.mapfile_mission_none"))
        self.status_label.setText("\n".join(lines))
        self._sync_buttons()

    def _pick_pbo(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self.widget, tr("bgp.pbo_dlg"), self.folder_edit.text().strip(),
            tr("bgp.pbo_filter"))
        if path:
            self.pbo_combo.insertItem(0, os.path.basename(path), path)
            self.pbo_combo.setCurrentIndex(0)

    def _fill_unpacked(self, keep_paths: bool = False) -> None:
        """Добавить в список уже распакованные миры — их можно открыть без PBO.

        Мир, чей архив только что нашёлся сканом, второй раз не показываем: открыть его
        можно и с той строки, а распаковать заново — только с неё."""
        if not keep_paths:
            self.pbo_combo.clear()
        listed = {self.pbo_combo.itemData(i) for i in range(self.pbo_combo.count())}
        listed |= {tiles_unpack.world_name_from_pbo(data) for data in listed
                   if isinstance(data, str) and os.path.isfile(data)}
        for world in tiles_store.available_worlds():
            if world not in listed:
                self.pbo_combo.addItem(tr("src.mapfile_unpacked_item", world=world), world)

    def _on_pbo_selected(self, _index: int) -> None:
        data = self.pbo_combo.currentData()
        if not data:
            return
        self.name_edit.setText(tiles_unpack.world_name_from_pbo(data)
                               if os.path.isfile(data) else data)
        self._sync_buttons()

    def _sync_buttons(self, *_args) -> None:
        data = self.pbo_combo.currentData() or ""
        world = self.name_edit.text().strip()
        self.unpack_button.setEnabled(bool(world) and os.path.isfile(data))
        self.open_button.setEnabled(bool(world) and tiles_store.find(world) is not None)

    # ---------- действия ----------

    def _unpack(self) -> None:
        path = self.pbo_combo.currentData() or ""
        world = self.name_edit.text().strip()
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            result = map_import.import_map(path, world, log=lambda _m: None)
        except tiles_unpack.UnpackError as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self.widget, tr("bgp.unpack_fail_title"), str(error))
            return
        finally:
            if QApplication.overrideCursor():
                QApplication.restoreOverrideCursor()
        meta = tiles_store.find(world)
        report = tr("src.mapfile_done", world=world,
                    size=int(meta.world_size) if meta else 0,
                    zoom=meta.max_zoom if meta else 0,
                    classes=result["classes"])
        if result["buildings_error"]:
            report += "\n" + tr("src.mapfile_no_buildings", err=result["buildings_error"])
        self.status_label.setText(report)
        QMessageBox.information(self.widget, tr("src.mapfile_done_title"), report)
        self._fill_unpacked(keep_paths=True)
        self._sync_buttons()

    def _open(self) -> None:
        world = self.name_edit.text().strip()
        path = self.pbo_combo.currentData() or ""
        self.emit_project(create_map_project(path if os.path.isfile(path) else "", world))


def create_map_project(pbo_path: str, world: str) -> P.Project:
    """Просмотр карты: ни миссии, ни файлов — одна ссылка на распакованную пирамиду.

    НЕ сохраняется: папки в appdata/projects не появляется и в списке недавних этого нет.
    Хранить нечего — всё содержимое уже лежит в appdata/tiles/<world>, а «проект» тут
    только чтобы редактор понимал, что открывать (см. `Project.is_map_only`)."""
    return P.Project(
        id=world,
        name=world,
        provider_cfg={"kind": "pbo", "pbo": os.path.abspath(pbo_path) if pbo_path else ""},
        mission_name="",
        files={},
        background=f"tiles:{world}")
