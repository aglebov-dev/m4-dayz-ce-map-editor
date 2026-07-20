"""Контракт «источника проекта» — вкладка приветственного окна, которая ЗАГРУЖАЕТ проект.

Источник самодостаточен и живёт в своём файле (в духе презентер-рефакторинга UI):
сам строит свою пассивную вкладку, сам проверяет свою доступность и сам решает, из чего
собрать `light.project.Project`. Приветственное окно только перебирает коллекцию источников
и по `availability()` решает, показывать вкладку и как (политика — в одном месте окна).

Это ОТДЕЛЬНЫЙ слой от `light.providers.DataProvider` (тот читает файлы сервера DayZ);
источники Folder/SFTP используют `DataProvider` внутри, но остальные (Recent, BI) — нет.

Добавление нового источника = новый класс + строка в `light.sources.SOURCES`."""
from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QWidget


@dataclass(frozen=True)
class Availability:
    """Доступен ли источник. `reason` — человекочитаемая причина недоступности
    (как её показывать — решает приветственное окно; см. `WelcomeWindow`)."""

    ok: bool
    reason: str = ""

    @classmethod
    def available(cls) -> "Availability":
        return cls(True)

    @classmethod
    def unavailable(cls, reason: str) -> "Availability":
        return cls(False, reason)


class ProjectSource(QObject):
    """Абстрактный источник проекта = одна вкладка приветственного окна.

    Наследник задаёт `id`/`title`, строит свою вкладку в `build_widget()` и, подготовив
    проект, эмитит `project_ready(Project)`. По желанию переопределяет `availability()`."""

    project_ready = Signal(object)

    id: str = "abstract"
    title: str = "Source"

    def availability(self) -> Availability:
        """Доступен ли источник сейчас (зависимости, окружение). По умолчанию — да."""
        return Availability.available()

    def build_widget(self) -> QWidget:
        """Содержимое вкладки (пассивная панель). Кнопки внутри эмитят `project_ready`."""
        raise NotImplementedError

    def emit_project(self, project) -> None:
        """Хелпер для наследников: отдать готовый проект приветственному окну."""
        self.project_ready.emit(project)
