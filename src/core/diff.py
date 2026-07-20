"""Дифф двух areaflags.map: где изменились тиры/usage.

ВАЖНО: флаги сопоставляются по ИМЕНАМ, а не по номерам битов. Порядок битов задаёт
cfglimitsdefinition.xml каждой миссии, и у редакторской карты он может отличаться от
боевой — сравнение «бит к биту» тогда врало бы молча."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.areaflags import AreaFlags


class DiffError(Exception):
    """Срезы несравнимы (разная сетка/размер мира)."""


@dataclass
class FlagDiff:
    key: str
    name: str
    added: int
    removed: int
    only_in: str | None

    @property
    def changed(self) -> int:
        return self.added + self.removed


@dataclass
class MapDiff:
    flags: list[FlagDiff]
    changed_cells: int
    cells: int
    cell_size: float
    grid_x: int
    grid_y: int

    @property
    def pct(self) -> float:
        return 100.0 * self.changed_cells / self.cells if self.cells else 0.0


def _plane(af: AreaFlags, name: str) -> np.ndarray | None:
    if name not in af.usages and name not in af.values:
        return None
    return af.plane(name)


def diff_planes(a: AreaFlags, b: AreaFlags, key: str) -> tuple[np.ndarray, np.ndarray]:
    """(появилось, пропало) — bool[grid_y, grid_x] для флага key ('usage:Military')."""
    name = key.split(":", 1)[1]
    pa, pb = _plane(a, name), _plane(b, name)
    zero = np.zeros((a.grid_y, a.grid_x), dtype=bool)
    if pa is None:
        pa = zero
    if pb is None:
        pb = zero
    return (pb & ~pa), (pa & ~pb)


def diff_maps(a: AreaFlags, b: AreaFlags) -> MapDiff:
    """a — срез «было» (текущая карта), b — срез «стало» (загруженный файл)."""
    if (a.grid_x, a.grid_y) != (b.grid_x, b.grid_y):
        raise DiffError(f"разная сетка: {a.grid_x}×{a.grid_y} и {b.grid_x}×{b.grid_y}")
    if (a.size_x, a.size_y) != (b.size_x, b.size_y):
        raise DiffError(f"разный размер мира: {a.size_x} и {b.size_x} м")

    flags: list[FlagDiff] = []
    changed = np.zeros(a.cells, dtype=bool)
    for names_a, names_b, prefix in ((a.values, b.values, "tier"),
                                     (a.usages, b.usages, "usage")):
        for name in list(names_a) + [n for n in names_b if n not in names_a]:
            in_a, in_b = name in names_a, name in names_b
            pa, pb = _plane(a, name), _plane(b, name)
            zero = np.zeros((a.grid_y, a.grid_x), dtype=bool)
            pa = zero if pa is None else pa
            pb = zero if pb is None else pb
            add = int(np.count_nonzero(pb & ~pa))
            rem = int(np.count_nonzero(pa & ~pb))
            changed |= (pa ^ pb).reshape(-1)
            flags.append(FlagDiff(
                f"{prefix}:{name}", name, add, rem,
                None if (in_a and in_b) else ("a" if in_a else "b")))
    return MapDiff(flags=flags, changed_cells=int(np.count_nonzero(changed)),
                   cells=a.cells, cell_size=a.cell_size,
                   grid_x=a.grid_x, grid_y=a.grid_y)
