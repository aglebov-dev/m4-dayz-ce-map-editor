"""Блокировка инструментов по наличию файлов. Чистая логика — тестируется без UI."""
from __future__ import annotations

from light.project import ROLES

# Инструмент -> роли файлов, без которых он не работает.
TOOL_REQUIRES = {
    "map": ["areaflags", "cfglimits"],          # Слои, инспектор слоёв
    "objects": ["mapgroupproto", "mapgrouppos"],  # Объекты, инспектор объектов
    "economy": ["economycore", "types"],        # Спавн/Предметы
    "territories": ["environment"],             # Территории
}

_TITLE = {r.key: r.title for r in ROLES}


def tool_status(files: dict) -> dict:
    """tool -> {'ok': bool, 'missing': [заголовки недостающих файлов]}."""
    out = {}
    for tool, need in TOOL_REQUIRES.items():
        miss = [_TITLE.get(k, k) for k in need if k not in files]
        out[tool] = {"ok": not miss, "missing": miss}
    return out


def tool_ok(files: dict, tool: str) -> bool:
    return not [k for k in TOOL_REQUIRES.get(tool, []) if k not in files]


def missing_for(files: dict, tool: str) -> list[str]:
    return [_TITLE.get(k, k) for k in TOOL_REQUIRES.get(tool, []) if k not in files]
