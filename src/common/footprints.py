"""Геометрия контуров зданий: (позиция, имя класса) → углы ориентированного
прямоугольника footprint в мировых координатах. Без Qt.

Каноничная формула ресёрча (DayZ-«компасная» матрица, проверена наложением на спутник),
`yaw` — ИСТИННЫЙ модельный поворот из датасета (там уже `yaw_deg = 90 − a`, где `a` —
атрибут mapgrouppos; поэтому здесь yaw берём как есть, без поправок):

    θ = radians(yaw)                       # 0 = север/+Z, по часовой
    px, pz = lx + ox, lz + oz              # локальные оси: X=вправо=w, Z=вперёд=l
    east   = x + px·cosθ + pz·sinθ
    north  = z − px·sinθ + pz·cosθ

Мир: X — восток, Z — север. Инверсию Z (север сверху) делает слой отображения.
"""
from __future__ import annotations

import numpy as np


# знаки полуразмеров для 4 углов: локальные X (w) и Z (l)
_SX = np.array([-1.0, 1.0, 1.0, -1.0])
_SZ = np.array([-1.0, -1.0, 1.0, 1.0])


def oriented_corners(x, z, names: list[str], index) -> tuple[np.ndarray, np.ndarray]:
    """Углы footprint для инстансов, у которых класс есть в датасете.

    x, z — позиции (восток/север), names — имена классов, index — BuildingIndex.
    Возвращает (corners, kept): corners формы (M, 4, 2) — мировые (X, Z) четырёх углов;
    kept — индексы (в исходном массиве) тех инстансов, для которых footprint нашёлся.
    Инстансы без footprint (нет класса в датасете) пропускаются.
    """
    x = np.asarray(x, dtype=np.float64)
    z = np.asarray(z, dtype=np.float64)
    keep: list[int] = []
    w: list[float] = []
    l: list[float] = []
    ox: list[float] = []
    oz: list[float] = []
    yaw: list[float] = []
    for i, name in enumerate(names):
        fp = index.footprint(name)
        if fp is None:
            continue
        keep.append(i)
        w.append(fp.w)
        l.append(fp.l)
        ox.append(fp.ox)
        oz.append(fp.oz)
        yaw.append(index.yaw(name, float(x[i]), float(z[i])))
    if not keep:
        return np.empty((0, 4, 2), dtype=np.float64), np.empty(0, dtype=np.int64)
    keep_arr = np.array(keep, dtype=np.int64)
    hw = np.array(w) / 2.0
    hl = np.array(l) / 2.0
    rad = np.radians(np.array(yaw))
    cos, sin = np.cos(rad), np.sin(rad)
    px = hw[:, None] * _SX[None, :] + np.array(ox)[:, None]     # (M, 4) локальный X + ox
    pz = hl[:, None] * _SZ[None, :] + np.array(oz)[:, None]     # локальный Z + oz
    east = x[keep_arr, None] + px * cos[:, None] + pz * sin[:, None]
    north = z[keep_arr, None] - px * sin[:, None] + pz * cos[:, None]
    corners = np.stack([east, north], axis=-1)                  # (M, 4, 2)
    return corners, keep_arr
