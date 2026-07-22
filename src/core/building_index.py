"""Датасет зданий — bundled-ассет `assets/buildings/<world>.json`. Нужен ТОЛЬКО ради
габаритов (footprint) модели по имени класса — их нет в mapgrouppos.

Наработка ресёрча (`dayz-research/DATA/buildings`): по каждому классу — ориентированный
bounding box модели (footprint w×l, высота h, смещение центра ox/oz из `.p3d`). Позицию и
угол каждого инстанса берём НЕ отсюда, а из загруженного mapgrouppos (`core.groups`) — там
истинный yaw в т.ч. кастомных зданий (DayZ Editor). Геометрия контуров — в `common.footprints`.
Без Qt.

Имя класса в датасете == имя `<group name=...>` в mapgrouppos/mapgroupproto → footprint
матчится к зданию по имени 1:1 (надёжно, без привязки к позициям)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Footprint:
    w: float     # размер по локальной оси X (м)
    l: float     # размер по локальной оси Z (м)
    ox: float    # смещение центра bbox от origin модели по X
    oz: float    # по Z


class BuildingIndex:
    """footprint (габариты) по имени класса. Один на мир."""

    def __init__(self, world: str, world_size: int, footprints: dict[str, Footprint]):
        self.world = world
        self.world_size = world_size
        self._footprints = footprints

    def footprint(self, name: str) -> Footprint | None:
        return self._footprints.get(name)

    def __bool__(self) -> bool:
        return bool(self._footprints)


SHARED = "_shared.json"      # общая библиотека классов, не привязанная к миру


def load_index(roots, world: str) -> BuildingIndex | None:
    """Собрать footprint-таблицу по всем `roots` (папка или список).

    В каждом корне читаем сначала `_shared.json` (общая библиотека — габариты моделей,
    накопленные распаковками любых карт), затем `<world>.json` поверх него. Порядок корней
    = приоритет (обычно appdata → bundled): раньше в списке = важнее. Датасеты ОБЪЕДИНЯЮТСЯ,
    одноимённый класс из более приоритетного источника побеждает. None — если не найдено
    ни одного файла."""
    if isinstance(roots, (str, Path)):
        roots = [roots]
    footprints: dict[str, Footprint] = {}
    world_size = 0
    found = False
    for root in reversed(list(roots)):           # низший приоритет первым, важный поверх
        for name in (SHARED, f"{world}.json"):   # общее, затем набор карты поверх него
            path = Path(root) / name
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            found = True
            world_size = int(data.get("worldSize", 0)) or world_size
            for c in data.get("classes", []):
                fp = c.get("footprint")
                if fp:
                    footprints[c["name"]] = Footprint(fp["w"], fp["l"],
                                                      fp.get("ox", 0.0), fp.get("oz", 0.0))
    return BuildingIndex(world, world_size, footprints) if found else None
