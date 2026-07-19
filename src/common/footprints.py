"""Геометрия контуров зданий: (позиция, имя класса) → углы ориентированного
прямоугольника footprint в мировых координатах. Без Qt.

    центр  = (x + ox, z + oz)
    угол   = центр + Rz(90° − yaw)·(±w/2, ±l/2)
Мир: X — восток, Z — север. Инверсию Z (север сверху) делает слой отображения.

ВАЖНО про угол: `yaw` (атрибут `a` в mapgrouppos) — это КОМПАСНЫЙ курс DayZ (по часовой
от севера), а не математический угол. В нашу CCW-от-востока формулу он переводится как
(90° − yaw). Ресёрчевский `render_preview.py` брал yaw как есть и был визуально «ок» лишь
потому, что валидировался при 10 м/пиксель — на этом масштабе разворот отдельного здания
не виден. Проверено наложением на спутник (вагоны вдоль ж/д, дома по кровлям): (90−yaw)
садит контуры точно на крыши, сырой yaw разворачивает часть зданий на 90°.
"""
from __future__ import annotations

import numpy as np


# порядок углов: ЮЗ, ЮВ, СВ, СЗ в локальных осях (знаки полуразмеров)
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
    cx = x[keep_arr] + np.array(ox)
    cz = z[keep_arr] + np.array(oz)
    rad = np.radians(90.0 - np.array(yaw))     # yaw = компасный курс → CCW-от-востока

    cos, sin = np.cos(rad), np.sin(rad)
    dx = hw[:, None] * _SX[None, :]            # (M, 4)
    dz = hl[:, None] * _SZ[None, :]
    wx = cx[:, None] + dx * cos[:, None] - dz * sin[:, None]
    wz = cz[:, None] + dx * sin[:, None] + dz * cos[:, None]
    corners = np.stack([wx, wz], axis=-1)      # (M, 4, 2)
    return corners, keep_arr
