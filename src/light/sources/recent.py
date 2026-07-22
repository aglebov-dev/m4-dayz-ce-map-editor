"""Источник «Недавние проекты» — ранее созданные проекты приложения (appdata/projects).

Главная вкладка приветственного окна: список готовых проектов, двойной клик / «Открыть»
загружает выбранный через `Project.load`. Ничего не материализует — данные уже локальны."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from light import project as P
from light.sources.base import Availability, ProjectSource


class RecentProjectSource(ProjectSource):
    id = "recent"
    title = "src.recent"

    def availability(self) -> Availability:
        """Доступен, только если есть хотя бы один сохранённый проект — иначе показывать
        пустую вкладку незачем (причину окно покажет пользователю)."""
        if P.list_projects():
            return Availability.available()
        return Availability.unavailable(tr("src.recent_none"))

    def build_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        layout.addWidget(QLabel(tr("welcome.recent_label")))

        self.list_widget = QListWidget()
        for config in P.list_projects():
            title = config.get("name") or config.get("id", "?")
            mission = config.get("mission_rel", "")
            label = f"{title}   —   {mission}" if mission else title
            item = QListWidgetItem(label)
            item.setData(0x0100, config.get("id"))   # Qt.UserRole
            self.list_widget.addItem(item)
        self.list_widget.itemDoubleClicked.connect(lambda _item: self._open())
        self.list_widget.currentItemChanged.connect(self._refresh_button)
        layout.addWidget(self.list_widget, 1)

        self.open_button = QPushButton(tr("welcome.open_button"))
        self.open_button.clicked.connect(self._open)
        layout.addWidget(self.open_button)

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        self._refresh_button()
        return widget

    def _refresh_button(self, *_args) -> None:
        self.open_button.setEnabled(self.list_widget.currentItem() is not None)

    def _open(self) -> None:
        item = self.list_widget.currentItem()
        if item is None:
            return
        project = P.Project.load(item.data(0x0100))
        self.emit_project(project)
