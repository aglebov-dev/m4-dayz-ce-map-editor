"""Единый подбор цвета слоя для ВСЕХ фич (слои, объекты, зоны, статистика, экспорт, дифф).

Раньше это был метод `MainWindow.layer_color` — вынесено в common, чтобы фичи не тянули
логику из god-окна. Зависимости передаются ЯВНО (без ссылки на MainWindow):
- settings          — источник пользовательских переопределений цвета (по имени миссии);
- mission()         — текущая миссия (для области настроек);
- areaflags()       — текущая карта (порядок битов флагов);
- territory_colors  — цвета территорий по умолчанию (из файлов env), заполняется загрузкой.
"""
from __future__ import annotations

from typing import Callable

from common.palette import tier_color, usage_color

RGB = tuple[int, int, int]


class LayerColors:
    def __init__(self, *, settings, mission: Callable, areaflags: Callable,
                 territory_colors: dict[str, RGB]):
        self._settings = settings
        self._mission = mission
        self._areaflags = areaflags
        self._territory_colors = territory_colors

    def color(self, key: str) -> RGB:
        """Цвет слоя `key` (tier:/usage:/terr:/obj:…): переопределение или дефолт по флагу."""
        mission = self._mission()
        if mission:
            saved = self._settings.layer_color(mission.name, key)
            if saved:
                return saved
        parts = key.split(":")
        areaflags = self._areaflags()
        if parts[0] == "terr":
            return self._territory_colors.get(key, (255, 140, 0))
        if parts[0] == "tier":
            return tier_color(areaflags.values, areaflags.values.index(parts[1]))
        if parts[0] == "usage":
            return usage_color(parts[1], areaflags.usages.index(parts[1]))
        if parts[0] == "obj" and len(parts) == 3:        # здания по флагу — в цвет флага
            if parts[1] == "tier":
                return tier_color(areaflags.values, areaflags.values.index(parts[2]))
            return usage_color(parts[2], areaflags.usages.index(parts[2]))
        return (0, 229, 255)                             # obj:buildings — циан по умолчанию
