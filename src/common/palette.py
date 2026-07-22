"""Палитра флагов CE и подбор цвета по имени/биту. Чистые данные + функции (без Qt),
поэтому живут в common и переиспользуются слоями, экспортом, дифом и т.д.

Реэкспортируется из `ui.overlays` для обратной совместимости старых импортов."""
from __future__ import annotations

import colorsys

# Цвета тиров по имени value-флага (RGB). Неизвестные имена получат цвета из запаски.
TIER_COLORS = {
    "Tier1": (76, 175, 80),      # зелёный
    "Tier2": (255, 235, 59),     # жёлтый
    "Tier3": (255, 152, 0),      # оранжевый
    "Tier4": (244, 67, 54),      # красный
    "Unique": (156, 39, 176),    # фиолетовый
}
FALLBACK_COLORS = [(0, 188, 212), (233, 30, 99), (121, 85, 72), (63, 81, 181)]

# Цвета usage-флагов по имени; неизвестным именам — запаска по золотому сечению оттенка.
USAGE_COLORS = {
    "Military": (229, 57, 53),        # красный
    "Police": (30, 136, 229),         # синий
    "Medic": (236, 64, 122),          # розовый
    "Firefighter": (255, 112, 67),    # оранж-красный
    "Industrial": (141, 110, 99),     # коричневый
    "Farm": (192, 202, 51),           # лаймовый
    "Coast": (38, 198, 218),          # циан
    "Town": (171, 71, 188),           # пурпурный
    "Village": (255, 167, 38),        # оранжевый
    "Hunting": (102, 187, 106),       # зелёный
    "Office": (92, 107, 192),         # индиго
    "School": (255, 238, 88),         # жёлтый
    "Prison": (120, 144, 156),        # серо-синий
    "Lunapark": (255, 138, 216),      # светло-розовый
    "SeasonalEvent": (255, 241, 118), # светло-жёлтый
    "ContaminatedArea": (124, 179, 66),  # ядовито-зелёный
    "Historical": (161, 136, 127),    # какао
    "Underground": (69, 90, 100),     # тёмный сине-серый
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
