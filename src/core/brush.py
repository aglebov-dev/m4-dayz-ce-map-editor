"""Кисть по битплану: круглый штамп, ластик, undo/redo патчами.

Патч — прямоугольный кусок плоскости ДО правки (bbox мазка). Мазки мелкие, поэтому
история дешёвая: хранится не вся карта, а только затронутые ячейки.
Правки живут в памяти; запись areaflags.map на диск — этап 12."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

MAX_HISTORY = 200                    # шагов undo (мазок = шаг)


@dataclass
class Patch:
    """Кусок плоскости до и после правки: (col0, row0) — левый нижний угол."""
    key: str
    col0: int
    row0: int
    before: np.ndarray
    after: np.ndarray

    @property
    def cells(self) -> int:
        return int(np.count_nonzero(self.before != self.after))


def plane_array(af, key: str) -> tuple[np.ndarray, int]:
    """(2D-вид массива флагов, номер бита) для ключа 'usage:Military' / 'tier:Tier3'."""
    prefix, name = key.split(":", 1)
    if prefix == "usage":
        return af.usage.reshape(af.grid_y, af.grid_x), af.usages.index(name)
    return af.tier.reshape(af.grid_y, af.grid_x), af.values.index(name)


def circle_bbox(af, x: float, z: float, radius_m: float) -> tuple[int, int, int, int]:
    """Ячейковый bbox круга (col0, row0, col1, row1), обрезанный по карте."""
    cs = af.cell_size
    c0 = int(np.floor((x - radius_m) / cs))
    c1 = int(np.floor((x + radius_m) / cs))
    r0 = int(np.floor((z - radius_m) / cs))
    r1 = int(np.floor((z + radius_m) / cs))
    return (max(0, c0), max(0, r0), min(af.grid_x - 1, c1), min(af.grid_y - 1, r1))


def stamp(af, key: str, x: float, z: float, radius_m: float,
          erase: bool = False) -> Patch | None:
    """Круглый мазок в мировой точке."""
    return stroke(af, key, x, z, x, z, radius_m, erase)


def stroke(af, key: str, x0: float, z0: float, x1: float, z1: float,
           radius_m: float, erase: bool = False) -> Patch | None:
    """Мазок по ОТРЕЗКУ (x0,z0)-(x1,z1) — «капсула» радиуса radius_m.

    Мышь между событиями move проскакивает десятки метров, и отдельными кругами
    получался пунктир. Красим ячейки, чей центр ближе radius_m к отрезку — один
    патч на всю капсулу, без швов и без лишних перерисовок.
    None — если ничего не изменилось (вне карты или бит уже такой)."""
    lo_x, hi_x = sorted((x0, x1))
    lo_z, hi_z = sorted((z0, z1))
    c0, r0, _, _ = circle_bbox(af, lo_x, lo_z, radius_m)
    _, _, c1, r1 = circle_bbox(af, hi_x, hi_z, radius_m)
    if c0 > c1 or r0 > r1:
        return None                              # капсула целиком вне карты
    arr, bit = plane_array(af, key)
    sub = arr[r0:r1 + 1, c0:c1 + 1]
    before = sub.copy()
    cs = af.cell_size
    px = (np.arange(c0, c1 + 1) + 0.5) * cs      # центры ячеек, метры
    pz = (np.arange(r0, r1 + 1) + 0.5) * cs
    dx, dz = x1 - x0, z1 - z0
    len2 = dx * dx + dz * dz
    ax = px[None, :] - x0
    az = pz[:, None] - z0
    if len2 <= 1e-9:                             # вырожденный отрезок = круг
        d2 = ax ** 2 + az ** 2
    else:                                        # расстояние до отрезка (t зажат в [0,1])
        t = np.clip((ax * dx + az * dz) / len2, 0.0, 1.0)
        d2 = (ax - t * dx) ** 2 + (az - t * dz) ** 2
    inside = d2 <= radius_m * radius_m
    mask = np.asarray(1 << bit, dtype=sub.dtype)
    if erase:
        sub[inside] &= ~mask
    else:
        sub[inside] |= mask
    if np.array_equal(before, sub):
        return None                              # мазок ничего не поменял
    return Patch(key, c0, r0, before, sub.copy())


class History:
    """Undo/redo по шагам. ШАГ — это весь мазок (список патчей от нажатия до отпускания
    ЛКМ), а не отдельный штамп: иначе одно движение мышью съедало бы десятки undo.
    Новый мазок обрубает ветку redo — как в любом редакторе."""

    def __init__(self, limit: int = MAX_HISTORY):
        self._undo: list[list[Patch]] = []
        self._redo: list[list[Patch]] = []
        self._limit = limit

    def push(self, step: list[Patch]):
        if not step:
            return
        self._undo.append(step)
        del self._undo[:-self._limit]
        self._redo.clear()

    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def depth(self) -> tuple[int, int]:
        return len(self._undo), len(self._redo)

    def clear(self):
        self._undo.clear()
        self._redo.clear()

    def undo(self, af) -> list[Patch] | None:
        """Откатывает весь мазок. Патчи внутри шага накладывались по очереди и могут
        перекрываться — откатываем в ОБРАТНОМ порядке, иначе поздний патч вернул бы
        состояние, которое уже успел испортить более ранний."""
        if not self._undo:
            return None
        step = self._undo.pop()
        for p in reversed(step):
            self._apply(af, p, p.before)
        self._redo.append(step)
        return step

    def redo(self, af) -> list[Patch] | None:
        if not self._redo:
            return None
        step = self._redo.pop()
        for p in step:                           # накат — в исходном порядке
            self._apply(af, p, p.after)
        self._undo.append(step)
        return step

    @staticmethod
    def _apply(af, p: Patch, data: np.ndarray):
        arr, _ = plane_array(af, p.key)
        h, w = data.shape
        arr[p.row0:p.row0 + h, p.col0:p.col0 + w] = data
