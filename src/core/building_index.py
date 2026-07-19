"""Датасет зданий (footprint по миру) — bundled-ассет `assets/buildings/<world>.json`.

Наработка ресерча (`dayz-research/DATA/buildings`): по каждому классу из mapgrouppos —
ориентированный bounding box модели (footprint w×l, высота h, смещение центра ox/oz),
по каждому инстансу — поворот (yaw). Здесь только чтение и быстрый доступ; геометрия
контуров (углы прямоугольников) считается в `common.footprints`. Без Qt.

Имя класса в датасете == имя `<group name=...>` в mapgrouppos/mapgroupproto, поэтому
footprint матчится к зданию по имени 1:1, а yaw — по имени и позиции (у ванильной карты
позиции совпадают точно; у изменённой части зданий yaw не найдётся → 0, контур по осям).
"""
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
    """footprint по имени класса + yaw по (имя, позиция). Один на мир."""

    def __init__(self, world: str, world_size: int,
                 footprints: dict[str, Footprint], yaws: dict[tuple, float]):
        self.world = world
        self.world_size = world_size
        self._footprints = footprints
        self._yaws = yaws

    def footprint(self, name: str) -> Footprint | None:
        return self._footprints.get(name)

    def yaw(self, name: str, x: float, z: float) -> float:
        """Поворот инстанса (град). Ключ — округлённая позиция; нет совпадения → 0."""
        return self._yaws.get((name, round(x, 1), round(z, 1)), 0.0)

    def __bool__(self) -> bool:
        return bool(self._footprints)


def load_index(assets_dir, world: str) -> BuildingIndex | None:
    """Прочитать `<assets_dir>/<world>.json`. None — если датасета для мира нет."""
    path = Path(assets_dir) / f"{world}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    by_id = {c["id"]: c for c in data.get("classes", [])}
    footprints: dict[str, Footprint] = {}
    for c in data.get("classes", []):
        fp = c.get("footprint")
        if fp:
            footprints[c["name"]] = Footprint(fp["w"], fp["l"],
                                              fp.get("ox", 0.0), fp.get("oz", 0.0))
    yaws: dict[tuple, float] = {}
    for cid, x, z, yaw in data.get("instances", []):
        cls = by_id.get(cid)
        if cls is not None:
            yaws[(cls["name"], round(x, 1), round(z, 1))] = yaw
    return BuildingIndex(world, int(data.get("worldSize", 0)), footprints, yaws)
