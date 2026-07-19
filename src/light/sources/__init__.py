"""Реестр источников проекта для приветственного окна.

Каждый источник = отдельная вкладка (см. `base.ProjectSource`). Порядок в `SOURCES` =
порядок вкладок. Добавить способ загрузки = импортировать класс и дописать его в список —
приветственное окно подхватит автоматически и само решит по `availability()`, показывать
вкладку или нет."""
from __future__ import annotations

from light.sources.base import Availability, ProjectSource
from light.sources.recent import RecentProjectSource

# Порядок вкладок слева направо. Первый доступный становится активным.
SOURCES: list[type[ProjectSource]] = [
    RecentProjectSource,
]

__all__ = ["SOURCES", "ProjectSource", "Availability", "RecentProjectSource"]
