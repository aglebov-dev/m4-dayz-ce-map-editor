"""Палитра флагов CE и подбор цвета по имени/биту. Чистые данные + функции (без Qt),
поэтому живут в common и переиспользуются слоями, экспортом, дифом и т.д.

Реэкспортируется из `ui.overlays` для обратной совместимости старых импортов."""
from __future__ import annotations

import colorsys

TIER_COLORS = {
    "Tier1": (76, 175, 80),
    "Tier2": (255, 235, 59),
    "Tier3": (255, 152, 0),
    "Tier4": (244, 67, 54),
    "Unique": (156, 39, 176),
}
FALLBACK_COLORS = [(0, 188, 212), (233, 30, 99), (121, 85, 72), (63, 81, 181)]

USAGE_COLORS = {
    "Military": (229, 57, 53),
    "Police": (30, 136, 229),
    "Medic": (236, 64, 122),
    "Firefighter": (255, 112, 67),
    "Industrial": (141, 110, 99),
    "Farm": (192, 202, 51),
    "Coast": (38, 198, 218),
    "Town": (171, 71, 188),
    "Village": (255, 167, 38),
    "Hunting": (102, 187, 106),
    "Office": (92, 107, 192),
    "School": (255, 238, 88),
    "Prison": (120, 144, 156),
    "Lunapark": (255, 138, 216),
    "SeasonalEvent": (255, 241, 118),
    "ContaminatedArea": (124, 179, 66),
    "Historical": (161, 136, 127),
    "Underground": (69, 90, 100),
}


def usage_color(name: str, bit: int) -> tuple[int, int, int]:
    if name in USAGE_COLORS:
        return USAGE_COLORS[name]
    hue = (bit * 0.618033988749895) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.75, 0.95)
    return int(red * 255), int(green * 255), int(blue * 255)


def tier_color(values: list[str], bit: int) -> tuple[int, int, int]:
    name = values[bit]
    if name in TIER_COLORS:
        return TIER_COLORS[name]
    return FALLBACK_COLORS[bit % len(FALLBACK_COLORS)]
