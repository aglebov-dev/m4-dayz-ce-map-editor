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


def load_index(roots, world: str) -> BuildingIndex | None:
    """Прочитать `<root>/<world>.json` — первый найденный среди `roots` (папка или список
    папок; порядок = приоритет, обычно appdata → bundled). None — если датасета для мира нет."""
    if isinstance(roots, (str, Path)):
        roots = [roots]
    path = next((Path(r) / f"{world}.json" for r in roots
                 if (Path(r) / f"{world}.json").is_file()), None)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    footprints: dict[str, Footprint] = {}
    for c in data.get("classes", []):
        fp = c.get("footprint")
        if fp:
            footprints[c["name"]] = Footprint(fp["w"], fp["l"],
                                              fp.get("ox", 0.0), fp.get("oz", 0.0))
    return BuildingIndex(world, int(data.get("worldSize", 0)), footprints)
