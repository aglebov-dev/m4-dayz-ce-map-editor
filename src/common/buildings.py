"""Модель зданий CE: инстансы + эффективные маски спавна + типы. Без Qt.

Строится один раз на карту и разделяется потребителями: инспектор объектов, спавн,
предметы, статистика. Эффективные маски — формула спавна: usage инстанса = usage группы
(mapgroupproto) ∪ площадной usage ячейки (areaflags); value инстанса = тир ячейки ∪ value
группы. Так матчинг «предмет ↔ здание» считается один раз и векторно.
"""
from __future__ import annotations

import os

import numpy as np

from core.groups import read_buildings
from core.types import instances_for_item, items_for_building, read_types

BUILDING_PICK_M = 20.0


class BuildingsModel:
    def __init__(self, buildings, eff_u: np.ndarray, eff_v: np.ndarray, types):
        self.buildings = buildings
        self.eff_u = eff_u
        self.eff_v = eff_v
        self.types = types

    @classmethod
    def build(cls, mission_path: str, areaflags) -> "BuildingsModel | None":
        """Прочитать здания и типы, посчитать эффективные маски. None — если файлов
        зданий нет или их не удалось прочитать."""
        proto = os.path.join(mission_path, "mapgroupproto.xml")
        pos = os.path.join(mission_path, "mapgrouppos.xml")
        if not (os.path.isfile(proto) and os.path.isfile(pos)):
            return None
        try:
            buildings = read_buildings(mission_path, areaflags.usages, areaflags.values)
        except Exception:
            return None
        b, af = buildings, areaflags
        cell_index = ((b.z / af.cell_size).astype(np.int64) * af.grid_x
                      + (b.x / af.cell_size).astype(np.int64))
        group_u = np.array([b.protos[n].usage_mask for n in b.names], dtype=np.uint32)
        group_v = np.array([b.protos[n].value_mask for n in b.names], dtype=np.uint8)
        eff_u = group_u | af.usage[cell_index]
        eff_v = af.tier[cell_index] | group_v
        try:
            types = read_types(mission_path, af.usages, af.values)
        except Exception:
            types = None
        return cls(buildings, eff_u, eff_v, types)

    def layer_summary(self, areaflags) -> list[tuple[str, str | None, int]]:
        """Строки для панели obj-слоёв: [(key, name, count)]. У «без флагов» name=None
        (подпись подставит вызывающий — это UI/локаль). Пустые слои опускаются."""
        no_flags = int(np.count_nonzero((self.eff_u == 0) & (self.eff_v == 0)))
        rows: list[tuple[str, str | None, int]] = [("obj:buildings", None, no_flags)]
        for bit, name in enumerate(areaflags.values):
            count = int(np.count_nonzero(self.eff_v >> np.uint8(bit) & 1))
            if count:
                rows.append((f"obj:tier:{name}", name, count))
        for bit, name in enumerate(areaflags.usages):
            count = int(np.count_nonzero(self.eff_u >> np.uint32(bit) & 1))
            if count:
                rows.append((f"obj:usage:{name}", name, count))
        return rows

    def subset(self, key: str, areaflags) -> tuple:
        """(x, z, глобальные индексы) инстансов слоя `obj:…`: без флагов или по биту маски."""
        parts = key.split(":")
        if len(parts) == 2:
            selection = np.flatnonzero((self.eff_u == 0) & (self.eff_v == 0))
        elif parts[1] == "tier":
            bit = areaflags.values.index(parts[2])
            selection = np.flatnonzero(self.eff_v >> np.uint8(bit) & 1)
        else:
            bit = areaflags.usages.index(parts[2])
            selection = np.flatnonzero(self.eff_u >> np.uint32(bit) & 1)
        return self.buildings.x[selection], self.buildings.z[selection], selection

    def info_at_index(self, index: int, areaflags,
                      from_xz: tuple[float, float] | None = None) -> dict:
        """Полная инфо по инстансу (флаги/лут/позиция) для инспектора. `from_xz` — точка
        клика для расчёта расстояния (иначе dist=0)."""
        b, af = self.buildings, areaflags
        building_x, building_z = float(b.x[index]), float(b.z[index])
        proto = b.protos[b.names[index]]
        cell = int(building_z / af.cell_size) * af.grid_x + int(building_x / af.cell_size)
        cell_usage, cell_tier = int(af.usage[cell]), int(af.tier[cell])
        dist = 0.0
        if from_xz is not None:
            dist = ((building_x - from_xz[0]) ** 2 + (building_z - from_xz[1]) ** 2) ** 0.5
        return {
            "index": index, "name": proto.name, "dist": dist,
            "x": building_x, "z": building_z,
            "lootmax": proto.lootmax, "points": proto.points,
            "group_u": proto.usage_mask, "group_v": proto.value_mask,
            "cell_u": cell_usage, "cell_v": cell_tier,
            "eff_u": proto.usage_mask | cell_usage,
            "eff_v": cell_tier | proto.value_mask,
        }

    def nearest(self, x: float, z: float, areaflags) -> dict | None:
        """Ближайший лутабельный инстанс в радиусе + его эффективные флаги по формуле."""
        b, af = self.buildings, areaflags
        if b is None or af is None or not len(b.x):
            return None
        distances_sq = (b.x - x) ** 2 + (b.z - z) ** 2
        index = int(np.argmin(distances_sq))
        if float(distances_sq[index]) ** 0.5 > BUILDING_PICK_M:
            return None
        return self.info_at_index(index, af, from_xz=(x, z))

    def indices_near(self, x: float, z: float, radius: float) -> np.ndarray:
        """Глобальные индексы инстансов в радиусе `radius` от точки (стек для высоток)."""
        b = self.buildings
        if b is None or not len(b.x):
            return np.empty(0, dtype=np.int64)
        d2 = (b.x - x) ** 2 + (b.z - z) ** 2
        return np.flatnonzero(d2 <= radius * radius)

    def items_for(self, info: dict | None) -> list:
        """Предметы, которые могут заспавниться в выбранном здании (для спавн-панели)."""
        if not (self.types and info):
            return []
        proto = self.buildings.protos[info["name"]]
        return items_for_building(self.types, proto, info["eff_u"], info["eff_v"])

    def instances_for_items(self, names: list[str]) -> np.ndarray:
        """Объединённые индексы инстансов, где могут спавниться выбранные предметы (Items)."""
        if not (self.types and names):
            return np.empty(0, dtype=np.int64)
        parts = [instances_for_item(self.types[n], self.buildings, self.eff_u, self.eff_v)
                 for n in names if n in self.types]
        return np.unique(np.concatenate(parts)) if parts else np.empty(0, dtype=np.int64)
