"""Реестр источников проекта для приветственного окна.

Каждый источник = отдельная вкладка (см. `base.ProjectSource`). Порядок в `SOURCES` =
порядок вкладок. Добавить способ загрузки = импортировать класс и дописать его в список —
приветственное окно подхватит автоматически и само решит по `availability()`, показывать
вкладку или нет."""
from __future__ import annotations

from light.sources.base import Availability, ProjectSource
from light.sources.bi import BiProjectSource
from light.sources.folder import FolderProjectSource
from light.sources.recent import RecentProjectSource
from light.sources.sftp import SftpProjectSource

# Порядок вкладок слева направо. Первый доступный становится активным.
SOURCES: list[type[ProjectSource]] = [
    RecentProjectSource,
    FolderProjectSource,
    SftpProjectSource,
    BiProjectSource,
]

__all__ = [
    "SOURCES", "ProjectSource", "Availability",
    "RecentProjectSource", "FolderProjectSource", "SftpProjectSource",
    "BiProjectSource",
]
