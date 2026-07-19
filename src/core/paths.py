"""Единая точка работы с файловой системой приложения.

`AppPaths` — единственный источник правды о путях ПРИЛОЖЕНИЯ: ассеты (только чтение,
поставляются с кодом) и записываемые данные (проекты, снапшоты, кэш подложек, настройки).
Внешние данные (сервер DayZ) читаются отдельным слоем — `light.providers`.

Все пути — `pathlib.Path`. Готовый экземпляр `paths` создаётся при импорте; для тестов
или выноса данных можно собрать свой: `AppPaths(root=..., appdata=...)`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


class AppPaths:
    """Раскладка файлов приложения. По умолчанию корень определяется автоматически;
    `appdata` можно переопределить (тесты) — иначе берётся env `M4_HOME` или `<root>/appdata`."""

    def __init__(self, root: Path | str | None = None,
                 appdata: Path | str | None = None):
        self.root = Path(root).resolve() if root else self._detect_root()
        self._appdata = Path(appdata) if appdata else None

    @staticmethod
    def _detect_root() -> Path:
        """Корень приложения. Заморожено (exe) — папка рядом с exe; иначе — корень репы
        (этот файл: `src/core/paths.py` → на три уровня вверх)."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        return Path(__file__).resolve().parents[2]

    # ---- ассеты: только чтение, поставляются с приложением ----

    @property
    def assets(self) -> Path:
        return self.root / "assets"

    @property
    def i18n(self) -> Path:
        return self.assets / "i18n"

    @property
    def assets_tiles(self) -> Path:
        """Готовые (bundled) пирамиды подложек, поставляемые с приложением."""
        return self.assets / "tiles"

    # ---- записываемые данные приложения ----

    @property
    def appdata(self) -> Path:
        """Куда приложение ПИШЕТ: проекты, снапшоты, кэш подложек, настройки.
        Переопределяется env `M4_HOME` (тесты / вынос данных).
        TODO: убрать env — передавать путь явно (см. docs/PLAN.md)."""
        if self._appdata is not None:
            return self._appdata
        env = os.environ.get("M4_HOME")
        return Path(env) if env else self.root / "appdata"

    @property
    def projects(self) -> Path:
        return self.appdata / "projects"

    @property
    def tiles_cache(self) -> Path:
        """Кэш подложек, распакованных пользователем из файлов игры (writable)."""
        return self.appdata / "tiles"

    @property
    def settings_file(self) -> Path:
        return self.appdata / "settings.json"

    # ---- хелперы ----

    def project(self, project_id: str) -> Path:
        """Служебная папка конкретного проекта (конфиг, снапшот, материализованные данные)."""
        return self.projects / project_id

    def tile_roots(self) -> list[Path]:
        """Где искать готовые пирамиды подложек: сначала кэш, затем bundled."""
        return [self.tiles_cache, self.assets_tiles]

    @staticmethod
    def ensure(path: Path) -> Path:
        """Создать папку (со всеми родителями), если её нет; вернуть путь."""
        path.mkdir(parents=True, exist_ok=True)
        return path


# Единый экземпляр для всего приложения.
paths = AppPaths()
