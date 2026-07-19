"""Статистика карты: площади флагов по всей карте или по прямоугольной области.

Область задаётся ячейками (col0, row0, col1, row1) включительно, row 0 = ЮГ —
как везде в проекте."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

Region = tuple[int, int, int, int]       # col0, row0, col1, row1 (включительно)


@dataclass
class FlagStat:
    key: str             # "tier:Tier1" / "usage:Military" — как в панели слоёв
    name: str
    cells: int
    area_km2: float
    pct: float           # % от площади охвата (карта или выделение)


@dataclass
class MapStats:
    cells: int                       # ячеек в охвате
    area_km2: float
    flags: list[FlagStat]            # тиры, затем usage — порядок cfglimitsdefinition
    any_usage_cells: int             # ячеек хотя бы с одним usage
    any_tier_cells: int
    buildings: int = 0               # лутабельных инстансов в охвате


def clamp_region(af, region: Region) -> Region:
    """Область в границы карты; концы упорядочены."""
    c0, r0, c1, r1 = region
    c0, c1 = sorted((c0, c1))
    r0, r1 = sorted((r0, r1))
    return (max(0, c0), max(0, r0),
            min(af.grid_x - 1, c1), min(af.grid_y - 1, r1))


def region_from_world(af, x0: float, z0: float, x1: float, z1: float) -> Region:
    """Мировой прямоугольник (метры) -> ячейки, обрезано по карте."""
    cs = af.cell_size
    return clamp_region(af, (int(x0 // cs), int(z0 // cs),
                             int(x1 // cs), int(z1 // cs)))


def bit_counts(arr: np.ndarray, nbits: int) -> list[int]:
    """Ячеек с каждым битом 0..nbits-1.

    Через гистограмму БАЙТОВ: один проход на байт вместо прохода на каждый бит.
    На 16.7M ячеек — ~100 мс вместо ~390 (кисть пересчитывает это после каждого мазка).
    Порядок байтов little-endian — как и у ридера (`frombuffer` uint32)."""
    a = np.ascontiguousarray(arr).reshape(-1)    # срез региона копируется, вся карта — нет
    if a.dtype == np.uint8:
        cols = a.reshape(-1, 1)
    else:
        cols = a.view(np.uint8).reshape(-1, a.dtype.itemsize)
    vals = np.arange(256)
    hist: dict[int, np.ndarray] = {}
    out: list[int] = []
    for b in range(nbits):
        k, sh = divmod(b, 8)
        h = hist.get(k)
        if h is None:
            h = hist[k] = np.bincount(cols[:, k], minlength=256)
        out.append(int(h[((vals >> sh) & 1) == 1].sum()))
    return out


def _sub(a: np.ndarray, af, region: Region | None) -> np.ndarray:
    """Срез плоскости ячеек по области (или вся карта)."""
    grid = a.reshape(af.grid_y, af.grid_x)
    if region is None:
        return grid
    c0, r0, c1, r1 = region
    return grid[r0:r1 + 1, c0:c1 + 1]


def map_stats(af, region: Region | None = None,
              bld_x: np.ndarray | None = None,
              bld_z: np.ndarray | None = None) -> MapStats:
    """Площади всех флагов по карте или по области. Проценты — от площади охвата."""
    usage = _sub(af.usage, af, region)
    tier = _sub(af.tier, af, region)
    cells = int(usage.size)
    cell_km2 = af.cell_size * af.cell_size / 1_000_000
    area = cells * cell_km2
    flags: list[FlagStat] = []
    for arr, names, prefix in ((tier, af.values, "tier"),
                               (usage, af.usages, "usage")):
        for name, n in zip(names, bit_counts(arr, len(names))):
            flags.append(FlagStat(f"{prefix}:{name}", name, n, n * cell_km2,
                                  100.0 * n / cells if cells else 0.0))
    n_bld = 0
    if bld_x is not None and len(bld_x):
        if region is None:
            n_bld = len(bld_x)
        else:
            cs = af.cell_size
            c0, r0, c1, r1 = region
            m = ((bld_x >= c0 * cs) & (bld_x < (c1 + 1) * cs)
                 & (bld_z >= r0 * cs) & (bld_z < (r1 + 1) * cs))
            n_bld = int(np.count_nonzero(m))
    return MapStats(cells=cells, area_km2=area, flags=flags,
                    any_usage_cells=int(np.count_nonzero(usage)),
                    any_tier_cells=int(np.count_nonzero(tier)),
                    buildings=n_bld)


def buildings_in_region(af, b, region: Region) -> np.ndarray:
    """Глобальные индексы инстансов внутри области."""
    cs = af.cell_size
    c0, r0, c1, r1 = region
    m = ((b.x >= c0 * cs) & (b.x < (c1 + 1) * cs)
         & (b.z >= r0 * cs) & (b.z < (r1 + 1) * cs))
    return np.flatnonzero(m)


def items_for_region(types: dict, b, idx: np.ndarray, eff_u: np.ndarray,
                     eff_v: np.ndarray) -> list[tuple]:
    """Сводка спавна по области: [(ItemType, в скольких зданиях области возможен)],
    отсортировано как в панели здания (категория, имя).

    Считаем по УНИКАЛЬНЫМ тройкам (группа, eff_u, eff_v) — их сотни, а не тысячи
    инстансов. Объединять маски по группе нельзя: usage мог бы совпасть с одним
    инстансом, а value — с другим, и предмет попал бы в список ложно."""
    from core.types import items_for_building
    if not len(idx):
        return []
    names = np.asarray(b.names, dtype=object)[idx]
    proto_ids = np.unique(names, return_inverse=True)
    uniq_names, name_ix = proto_ids
    combo = np.stack([name_ix.astype(np.int64),
                      eff_u[idx].astype(np.int64),
                      eff_v[idx].astype(np.int64)], axis=1)
    uniq, counts = np.unique(combo, axis=0, return_counts=True)
    totals: dict[str, list] = {}                 # имя предмета -> [ItemType, зданий]
    for (ni, u, v), n in zip(uniq.tolist(), counts.tolist()):
        proto = b.protos.get(uniq_names[ni])
        if proto is None:
            continue
        for t in items_for_building(types, proto, int(u), int(v)):
            row = totals.get(t.name)
            if row is None:
                totals[t.name] = [t, n]
            else:
                row[1] += n
    out = [(t, n) for t, n in totals.values()]
    out.sort(key=lambda r: (r[0].category or "", r[0].name.lower()))
    return out
