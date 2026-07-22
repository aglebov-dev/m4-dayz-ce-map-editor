"""Пирамида тайлов подложки (схема CRM: {z}/{x}_{y}.jpg + meta.json)."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, replace


@dataclass
class TileMeta:
    root: str            # папка мира с уровнями зума
    tile_size: int
    max_zoom: int
    width: float         # сцена: единиц полного зума (worldSize + 2*margin)
    height: float
    world_size: int      # метры
    margin: float        # поле вокруг мира, в единицах сцены
    stretch: float = 1.0  # растяжение картинки: единиц сцены на пиксель пирамиды

    def scale_at(self, zoom: int) -> float:
        """Во сколько единиц сцены разворачивается пиксель уровня zoom.

        Пирамида нормализована на 1 px/м своего мира, а сцена меряется в метрах ТЕКУЩЕЙ
        карты, поэтому кроме уровня учитываем и растяжение (см. `fitted_to`)."""
        return float(1 << (self.max_zoom - zoom)) * self.stretch

    def fitted_to(self, world_size: int) -> "TileMeta":
        """Та же пирамида, натянутая на мир размером `world_size` метров.

        Размер мира знает areaflags — он и есть истина. У подложки он лишь ОЦЕНЁН по
        сетке тайлов (`sat_extract.estimate_world_size`), и оценка бывает грубее на
        пару сотен метров. Раньше несовпадение просто отменяло подложку; вместо этого
        растягиваем картинку на мир карты — так любая пирамида годится любой areaflags,
        а мелкая погрешность оценки заодно уходит."""
        if world_size <= 0 or self.world_size <= 0 or abs(world_size - self.world_size) < 1:
            return self
        k = world_size / self.world_size
        return replace(self, width=self.width * k, height=self.height * k,
                       margin=self.margin * k, world_size=world_size,
                       stretch=self.stretch * k)

    def world_to_px(self, x: float, z: float) -> tuple[float, float]:
        """Мир (x, z; z на север) -> пиксель полного зума (y вниз, север сверху)."""
        return self.margin + x, self.margin + (self.world_size - z)

    def px_to_world(self, px: float, py: float) -> tuple[float, float]:
        return px - self.margin, self.world_size - (py - self.margin)

    def tile_path(self, zoom: int, x: int, y: int) -> str:
        return os.path.join(self.root, str(zoom), f"{x}_{y}.jpg")

    def grid_size(self, zoom: int) -> tuple[int, int]:
        """Число колонок/строк тайлов на уровне (последние могут быть неполными)."""
        span = self.tile_size * self.scale_at(zoom)   # scene px на тайл
        return math.ceil(self.width / span), math.ceil(self.height / span)

    def zoom_for_scale(self, view_scale: float) -> int:
        """Уровень пирамиды под масштаб вью (screen px / scene px): ~1 px тайла на px экрана."""
        if view_scale <= 0:
            return 0
        z = round(self.max_zoom + math.log2(view_scale * self.stretch))
        return max(0, min(self.max_zoom, z))

    def tiles_in_rect(self, zoom: int, left: float, top: float,
                      right: float, bottom: float) -> list[tuple[int, int]]:
        """Индексы тайлов уровня, пересекающих прямоугольник сцены (в px полного зума)."""
        span = self.tile_size * self.scale_at(zoom)
        cols, rows = self.grid_size(zoom)
        x0 = max(0, math.floor(left / span))
        y0 = max(0, math.floor(top / span))
        x1 = min(cols - 1, math.floor(right / span))
        y1 = min(rows - 1, math.floor(bottom / span))
        return [(x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def find_tiles(assets_dir: str, world: str) -> TileMeta | None:
    root = os.path.join(assets_dir, world)
    meta_path = os.path.join(root, "meta.json")
    if not os.path.isfile(meta_path):
        return None
    m = json.load(open(meta_path, encoding="utf-8"))
    return TileMeta(
        root=root,
        tile_size=int(m.get("tileSize", 256)),
        max_zoom=int(m.get("maxZoom", 6)),
        width=int(m.get("width", 15392)),
        height=int(m.get("height", 15392)),
        world_size=int(m.get("worldSize", 15360)),
        margin=int(m.get("margin", 16)),
    )


def iter_zoom_tiles(meta: TileMeta, zoom: int):
    """Все тайлы уровня: (x, y, путь). x_y в именах: x — колонка, y — строка (север сверху)."""
    zdir = os.path.join(meta.root, str(zoom))
    if not os.path.isdir(zdir):
        return
    for fn in os.listdir(zdir):
        if not fn.endswith(".jpg"):
            continue
        stem = fn[:-4]
        try:
            xs, ys = stem.split("_")
            yield int(xs), int(ys), os.path.join(zdir, fn)
        except ValueError:
            continue
