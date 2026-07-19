"""Датасет зданий (footprint по миру) — bundled-ассет `assets/buildings/<world>.json`.

Наработка ресерча (`dayz-research/DATA/buildings`): по каждому классу из mapgrouppos —
ориентированный bounding box модели (footprint w×l, высота h, смещение центра ox/oz),
по каждому инстансу — поворот `yaw_deg` = ИСТИННЫЙ модельный yaw (в датасете уже `90 − a`,
где `a` — атрибут mapgrouppos). Здесь только чтение и быстрый доступ; геометрия контуров
считается в `common.footprints` по каноничной формуле ресёрча. Без Qt.

Имя класса в датасете == имя `<group name=...>` в mapgrouppos/mapgroupproto, поэтому
footprint матчится к зданию по имени 1:1, а yaw — по имени и БЛИЖАЙШЕЙ позиции (у ванильной
карты позиции совпадают; у изменённого сервером здания берём поворот ближайшего ванильного
той же модели). Точное округление позиции было хрупким (~16 % промахов на границах бакетов
float32 → yaw=0 → развёрнутые здания), поэтому матчинг — по сетке с допуском (см. yaw()).
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


# сторона ячейки грид-индекса поворотов (м) и допуск матчинга (м²). Округление до 0.1
# было ХРУПКИМ: на границе .x5 float32-позиция загруженного mapgrouppos съезжала в соседний
# бакет и yaw не находился у ~16% зданий → они рисовались с yaw=0 (развёрнуты). Теперь —
# ближайший инстанс того же класса в радиусе TOL (ванильная позиция совпадает точно; чуть
# сдвинутое сервером здание берёт поворот ближайшего ванильного той же модели).
_CELL = 1.0
_TOL2 = 2.5 * 2.5


class BuildingIndex:
    """footprint по имени класса + yaw по (имя, ближайшая позиция). Один на мир."""

    def __init__(self, world: str, world_size: int,
                 footprints: dict[str, Footprint], grid: dict):
        self.world = world
        self.world_size = world_size
        self._footprints = footprints
        self._grid = grid                # (name, ix, iz) -> list[(x, z, yaw)]

    def footprint(self, name: str) -> Footprint | None:
        return self._footprints.get(name)

    def yaw(self, name: str, x: float, z: float) -> float:
        """Поворот инстанса (град): ближайший в датасете того же класса в радиусе TOL;
        нет — 0.0 (контур по осям)."""
        ix, iz = int(round(x / _CELL)), int(round(z / _CELL))
        best_yaw, best_d2 = 0.0, _TOL2
        for dx in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for px, pz, pyaw in self._grid.get((name, ix + dx, iz + dz), ()):
                    d2 = (px - x) ** 2 + (pz - z) ** 2
                    if d2 < best_d2:
                        best_d2, best_yaw = d2, pyaw
        return best_yaw

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
    grid: dict = {}                    # (name, ix, iz) -> list[(x, z, yaw)]
    for cid, x, z, yaw in data.get("instances", []):
        cls = by_id.get(cid)
        if cls is None:
            continue
        key = (cls["name"], int(round(x / _CELL)), int(round(z / _CELL)))
        grid.setdefault(key, []).append((float(x), float(z), float(yaw)))
    return BuildingIndex(world, int(data.get("worldSize", 0)), footprints, grid)
