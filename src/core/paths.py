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


def _is_compiled() -> bool:
    """Собрано ли приложение: Nuitka/pyside6-deploy (`__compiled__` в globals модуля) или
    PyInstaller (`sys.frozen`). В обычном запуске из исходников — False."""
    return getattr(sys, "frozen", False) or "__compiled__" in globals()


def _exe_dir() -> Path:
    """Папка, где РЕАЛЬНО лежит exe на диске (НЕ временная папка распаковки onefile).
    В onefile `sys.executable`/`__file__` указывают во временную распаковку; настоящий exe —
    в `sys.argv[0]`. Признак onefile у Nuitka — выставленная env `NUITKA_ONEFILE_PARENT`
    (плюс на всякий случай смотрим `NUITKA_ONEFILE_BINARY`). Standalone-Nuitka/PyInstaller —
    `sys.executable` уже сам exe рядом с ассетами."""
    onefile_bin = os.environ.get("NUITKA_ONEFILE_BINARY")
    if onefile_bin:
        return Path(onefile_bin).resolve().parent
    if os.environ.get("NUITKA_ONEFILE_PARENT") and sys.argv and sys.argv[0]:
        return Path(sys.argv[0]).resolve().parent
    return Path(sys.executable).resolve().parent


def _is_writable(directory: Path) -> bool:
    """Можно ли создать папку и писать в неё (напр. установка в Program Files — нельзя)."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write_test"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        return True
    except Exception:
        return False


class AppPaths:
    """Раскладка файлов приложения. По умолчанию корень определяется автоматически;
    `appdata` можно переопределить (тесты) — иначе берётся env `M4_HOME` или `<root>/appdata`."""

    def __init__(self, root: Path | str | None = None,
                 appdata: Path | str | None = None):
        self.root = Path(root).resolve() if root else self._detect_root()
        self._appdata = Path(appdata) if appdata else None
        self._auto_appdata: Path | None = None    # кэш вычисленного пути (writable-проба)

    @staticmethod
    def _detect_root() -> Path:
        """Корень с ассетами. PyInstaller (`sys.frozen`) — папка рядом с exe. Nuitka/
        pyside6-deploy (`__compiled__`) — корень бандла: там модули лежат в корне, значит
        `core/paths.*` → на два уровня вверх (в onefile это распакованная временная папка,
        куда попадают и данные из `--include-data-dir`). Иначе dev — корень репы (`src/core/
        paths.py` → на три уровня вверх)."""
        if getattr(sys, "frozen", False):
            return Path(sys.executable).parent
        if "__compiled__" in globals():
            return Path(__file__).resolve().parent.parent
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

    @property
    def assets_buildings(self) -> Path:
        """Датасеты зданий (footprint по миру) — bundled, поставляются с приложением."""
        return self.assets / "buildings"

    # ---- записываемые данные приложения ----

    @property
    def appdata(self) -> Path:
        """Куда приложение ПИШЕТ: проекты, снапшоты, кэш подложек, настройки.
        Приоритет: явный аргумент конструктора → env `M4_HOME` → вычисленный путь.
        В СОБРАННОМ приложении — ПОРТАТИВНО: `<папка_exe>/appdata` (рядом с exe), чтобы всю
        программу с данными можно было переносить папкой/на флешке. Если рядом с exe писать
        нельзя (установка в Program Files и т.п.) — откат в `%LOCALAPPDATA%/M4DayZCEMapEditor`.
        В dev — `<root>/appdata`. Результат кэшируется (writable-проба один раз)."""
        if self._appdata is not None:
            return self._appdata
        env = os.environ.get("M4_HOME")
        if env:
            return Path(env)
        if self._auto_appdata is None:
            self._auto_appdata = self._compute_appdata()
        return self._auto_appdata

    def _compute_appdata(self) -> Path:
        if not _is_compiled():
            return self.root / "appdata"
        portable = _exe_dir() / "appdata"
        if _is_writable(portable):
            return portable                       # рядом с exe (портативно) — основной путь
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "M4DayZCEMapEditor"   # exe в read-only месте — служебная папка

    @property
    def projects(self) -> Path:
        return self.appdata / "projects"

    @property
    def tiles_cache(self) -> Path:
        """Кэш подложек, распакованных пользователем из файлов игры (writable)."""
        return self.appdata / "tiles"

    @property
    def buildings_cache(self) -> Path:
        """Датасеты зданий, добавленные/сгенерированные пользователем (writable) — приоритетнее
        bundled. Кладём сюда `<world>.json`, чтобы иметь здания не только для Chernarus."""
        return self.appdata / "buildings"

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

    def buildings_roots(self) -> list[Path]:
        """Где искать датасеты зданий: сначала appdata (пользовательские), затем bundled."""
        return [self.buildings_cache, self.assets_buildings]

    @staticmethod
    def ensure(path: Path) -> Path:
        """Создать папку (со всеми родителями), если её нет; вернуть путь."""
        path.mkdir(parents=True, exist_ok=True)
        return path


# Единый экземпляр для всего приложения.
paths = AppPaths()
