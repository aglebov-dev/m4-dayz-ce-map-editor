"""Общая панель конфигурации проекта: миссия → файлы → имя → подложка → сборка проекта.

Провайдер-агностична: получает уже ПОДКЛЮЧЁННЫЙ `DataProvider` (ФС или SFTP) через
`set_provider` и дальше сама находит миссии, показывает наличие файлов по ролям, собирает
`Project` (материализация + снапшот). Переиспользуется источниками Folder/SFTP приветственного
окна — вся детальная настройка живёт здесь, а источник отвечает только за ПОДКЛЮЧЕНИЕ."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from light import project as P
from light.gating import tool_status
from light.providers import DataProvider


class ConfigurePanel(QWidget):
    """Сигнал `ready_changed(bool)` — можно ли собрать проект. `build_project()` — собрать."""

    ready_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._provider: DataProvider | None = None
        self._provider_cfg: dict = {}
        self._missions: list[str] = []
        self._files: dict = {}
        self._background_image_path = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # --- миссия ---
        self.mission_combo = QComboBox()
        self.mission_combo.currentIndexChanged.connect(self._on_mission)
        mission_group = QGroupBox("Миссия")
        mission_layout = QVBoxLayout(mission_group)
        mission_layout.addWidget(self.mission_combo)
        layout.addWidget(mission_group)

        # --- имя проекта ---
        self.project_name_edit = QLineEdit()
        self.project_name_edit.setPlaceholderText("Имя проекта")
        self.project_name_edit.textChanged.connect(self._refresh_ready)
        name_group = QGroupBox("Проект")
        name_layout = QVBoxLayout(name_group)
        name_layout.addWidget(self.project_name_edit)
        layout.addWidget(name_group)

        # --- файлы ---
        self.files_list = QListWidget()
        self.tools_label = QLabel("")
        self.tools_label.setWordWrap(True)
        self.tools_label.setTextFormat(Qt.TextFormat.RichText)
        files_group = QGroupBox("Файлы проекта")
        files_layout = QVBoxLayout(files_group)
        files_layout.addWidget(QLabel("✔ загружен · ✖ отсутствует"))
        files_layout.addWidget(self.files_list, 1)
        files_layout.addWidget(self.tools_label)
        layout.addWidget(files_group, 1)

        # --- подложка (спутник) ---
        layout.addWidget(self._build_background_group())

    def _build_background_group(self) -> QWidget:
        self.background_combo = QComboBox()
        self.background_image_button = QPushButton("Выбрать изображение…")
        self.background_image_button.clicked.connect(self._pick_background_image)
        self.game_edit = QLineEdit()
        self.game_edit.setPlaceholderText("Папка клиента DayZ")
        self.game_button = QPushButton("Открыть папку")
        self.game_button.clicked.connect(self._pick_game)
        self.unpack_button = QPushButton("Распаковать")
        self.unpack_button.clicked.connect(self._unpack_background)

        group = QGroupBox("Подложка (спутник)")
        group_layout = QVBoxLayout(group)
        group_layout.addWidget(QLabel(
            "Масштабируется под размер мира из areaflags (км берутся из карты)."))
        source_row = QHBoxLayout()
        source_row.addWidget(QLabel("Источник:"))
        source_row.addWidget(self.background_combo, 1)
        source_row.addWidget(self.background_image_button)
        group_layout.addLayout(source_row)
        unpack_row = QHBoxLayout()
        unpack_row.addWidget(self.game_edit, 1)
        unpack_row.addWidget(self.game_button)
        unpack_row.addWidget(self.unpack_button)
        group_layout.addWidget(QLabel(
            "Распаковать пирамиду тайлов (спутник) из файлов игры "
            "(в служебную папку приложения):"))
        group_layout.addLayout(unpack_row)
        self._refresh_backgrounds()
        return group

    # ---------- провайдер ----------

    def set_provider(self, provider: DataProvider | None, provider_cfg: dict) -> None:
        """Задать подключённый провайдер и его конфигурацию. Находит миссии и заполняет
        комбобокс; при None — очищает панель."""
        self._provider = provider
        self._provider_cfg = dict(provider_cfg)
        self._missions = P.find_missions(provider) if provider else []
        self.mission_combo.blockSignals(True)
        self.mission_combo.clear()
        if not self._missions:
            self.mission_combo.addItem("миссии не найдены", None)
        else:
            for mission in self._missions:
                self.mission_combo.addItem(mission or "(корень)", mission)
        self.mission_combo.blockSignals(False)
        self._on_mission()

    def clear(self) -> None:
        self.set_provider(None, {})

    # ---------- миссия и файлы ----------

    def _on_mission(self, *_args) -> None:
        self._files = {}
        self.files_list.clear()
        if not self._provider or not self._missions:
            self._refresh_ready()
            return
        mission_rel = self.mission_combo.currentData()
        if mission_rel is None:
            self._refresh_ready()
            return
        self._files = P.resolve_files(self._provider, mission_rel)
        for role in P.ROLES:
            present = role.key in self._files
            mark = "✔" if present else "✖"
            required = " (обязателен)" if role.required else ""
            item = QListWidgetItem(f"{mark}  {role.title}{required}")
            item.setForeground(Qt.GlobalColor.darkGreen if present else Qt.GlobalColor.gray)
            self.files_list.addItem(item)
        # имя по умолчанию — из папки миссии, если пользователь не задал своё
        if not self.project_name_edit.text().strip():
            default = os.path.basename(mission_rel.rstrip("/")) or "map_project"
            self.project_name_edit.setPlaceholderText(default)
        self._update_tools()
        self._refresh_ready()

    def _update_tools(self) -> None:
        status = tool_status(self._files)
        names = {"map": "Карта/Слои", "objects": "Объекты", "economy": "Спавн",
                 "territories": "Территории"}
        parts = []
        for tool, state in status.items():
            if state["ok"]:
                parts.append(f"<span style='color:green'>✔ {names[tool]}</span>")
            else:
                parts.append(f"<span style='color:#b26a00'>✖ {names[tool]} "
                             f"(нет: {', '.join(state['missing'])})</span>")
        self.tools_label.setText("Инструменты: " + " · ".join(parts))

    # ---------- подложка ----------

    def _refresh_backgrounds(self, keep: str = "") -> None:
        from light import tiles_store
        self.background_combo.blockSignals(True)
        self.background_combo.clear()
        self.background_combo.addItem("Нет", "")
        for world in tiles_store.available_worlds():
            self.background_combo.addItem(f"{world} (спутник)", f"tiles:{world}")
        if self._background_image_path:
            self.background_combo.addItem(
                f"изображение: {os.path.basename(self._background_image_path)}",
                f"image:{self._background_image_path}")
        index = self.background_combo.findData(keep or "")
        self.background_combo.setCurrentIndex(max(0, index))
        self.background_combo.blockSignals(False)

    def _pick_background_image(self) -> None:
        path, _filter = QFileDialog.getOpenFileName(
            self, "Изображение подложки", "", "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self._background_image_path = path
            self._refresh_backgrounds(keep=f"image:{path}")

    def _pick_game(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка DayZ")
        if folder:
            self.game_edit.setText(folder)

    def _unpack_background(self) -> None:
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        from light import tiles_unpack
        game = self.game_edit.text().strip()
        mission_rel = self.mission_combo.currentData()
        if not self._provider or mission_rel is None:
            QMessageBox.information(self, "Распаковка",
                                    "Сначала подключите источник и выберите миссию.")
            return
        world = P.world_name(mission_rel)
        size = P.read_world_size(self._provider, mission_rel) or 15360
        if not tiles_unpack.available():
            QMessageBox.warning(
                self, "Распаковка",
                "Нужен .NET SDK 10+ (dotnet) и скрипт ExtractSatMap.cs.\n"
                f"Скрипт: {tiles_unpack.script_path()}")
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            tiles_unpack.unpack(game, world, size)
        except tiles_unpack.UnpackError as error:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Распаковка подложки", str(error))
            return
        QApplication.restoreOverrideCursor()
        self._refresh_backgrounds(keep=f"tiles:{world}")
        QMessageBox.information(self, "Распаковка",
                                f"Подложка мира «{world}» ({size} м) распакована.")

    # ---------- готовность и сборка ----------

    def is_ready(self) -> bool:
        return bool(self._provider and self._files
                    and not P.missing_required(self._files))

    def _refresh_ready(self) -> None:
        self.ready_changed.emit(self.is_ready())

    def build_project(self) -> P.Project | None:
        """Собрать проект из выбранного: материализация + снапшот. None при ошибке."""
        if not self.is_ready():
            return None
        mission_name = self.mission_combo.currentData() or ""
        name = (self.project_name_edit.text().strip()
                or self.project_name_edit.placeholderText().strip()
                or "map_project")
        project = P.Project(
            id=_new_id(name),
            name=name,
            provider_cfg=dict(self._provider_cfg),
            mission_name=mission_name,
            files=dict(self._files),
            background=self.background_combo.currentData() or "")
        try:
            project.save()
            P.materialize(project, self._provider)
            P.make_snapshot(project)
        except Exception as error:
            QMessageBox.critical(self, "Проект", f"Не удалось подготовить проект: {error}")
            return None
        return project


def _new_id(name: str) -> str:
    from core.paths import paths
    base = "".join(c if c.isalnum() else "_" for c in name)[:32] or "proj"
    project_id, number = base, 2
    while paths.project(project_id).is_dir():
        project_id = f"{base}_{number}"
        number += 1
    return project_id
