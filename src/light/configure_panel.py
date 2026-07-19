"""Общая панель конфигурации проекта: миссия → файлы → имя → подложка → сборка проекта.

Провайдер-агностична: получает уже ПОДКЛЮЧЁННЫЙ `DataProvider` (ФС или SFTP) через
`set_provider` и дальше сама находит миссии, показывает наличие файлов по ролям, собирает
`Project` (материализация + снапшот). Переиспользуется источниками Folder/SFTP приветственного
окна — вся детальная настройка живёт здесь, а источник отвечает только за ПОДКЛЮЧЕНИЕ.
Подложку выбирает общий `BackgroundPanel`."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QGroupBox, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QVBoxLayout, QWidget,
)

from light import project as P
from light.background_panel import BackgroundPanel
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

        # --- подложка (общий виджет) ---
        self.background_panel = BackgroundPanel()
        layout.addWidget(self.background_panel)

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
        # мир для распаковки тайлов подложки
        self.background_panel.set_world(
            P.world_name(mission_rel),
            P.read_world_size(self._provider, mission_rel) or 15360)
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
            id=P.new_id(name),
            name=name,
            provider_cfg=dict(self._provider_cfg),
            mission_name=mission_name,
            files=dict(self._files),
            background=self.background_panel.value())
        try:
            project.save()
            P.materialize(project, self._provider)
            P.make_snapshot(project)
        except Exception as error:
            QMessageBox.critical(self, "Проект", f"Не удалось подготовить проект: {error}")
            return None
        return project
