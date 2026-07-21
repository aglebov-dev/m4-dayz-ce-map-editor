"""Фигуры-заливки по битплану: прямоугольник, эллипс, полигон (он же лассо).

Все координаты — мировые метры; ячейка попадает в фигуру, если её ЦЕНТР внутри
(так же, как у кисти). Возвращают Patch из core.brush — историю ведёт та же машинка."""
from __future__ import annotations

import numpy as np

from core.brush import Patch, plane_array

# полигон тоньше этого (в метрах по узкой стороне bbox) считаем линией, а не фигурой
MIN_SHAPE_M = 0.5


def _bbox_cells(af, x0: float, z0: float, x1: float, z1: float):
    """Ячейковый bbox мирового прямоугольника, обрезанный по карте."""
    cs = af.cell_size
    c0 = max(0, int(np.floor(min(x0, x1) / cs)))
    c1 = min(af.grid_x - 1, int(np.floor(max(x0, x1) / cs)))
    r0 = max(0, int(np.floor(min(z0, z1) / cs)))
    r1 = min(af.grid_y - 1, int(np.floor(max(z0, z1) / cs)))
    return c0, r0, c1, r1


def _cell_centers(af, c0: int, r0: int, c1: int, r1: int):
    cs = af.cell_size
    xs = (np.arange(c0, c1 + 1) + 0.5) * cs
    zs = (np.arange(r0, r1 + 1) + 0.5) * cs
    return xs, zs


def rect_mask(af, x0, z0, x1, z1):
    """(маска, c0, r0) прямоугольника."""
    c0, r0, c1, r1 = _bbox_cells(af, x0, z0, x1, z1)
    if c0 > c1 or r0 > r1:
        return None, 0, 0
    xs, zs = _cell_centers(af, c0, r0, c1, r1)
    lo_x, hi_x = sorted((x0, x1))
    lo_z, hi_z = sorted((z0, z1))
    inside_x = (xs >= lo_x) & (xs <= hi_x)
    inside_z = (zs >= lo_z) & (zs <= hi_z)
    return inside_z[:, None] & inside_x[None, :], c0, r0


def ellipse_mask(af, x0, z0, x1, z1, angle: float = 0.0):
    """(маска, c0, r0) эллипса, вписанного в прямоугольник растяжки.

    angle — поворот вокруг центра, радианы против часовой в МИРОВЫХ осях (x на восток,
    z на север). Прямоугольник (x0,z0)-(x1,z1) задаёт полуоси до поворота."""
    cx, cz = (x0 + x1) / 2, (z0 + z1) / 2
    rx, rz = abs(x1 - x0) / 2, abs(z1 - z0) / 2
    if rx <= 0 or rz <= 0:
        return None, 0, 0                        # вырожденный: линия, а не фигура
    cos_a, sin_a = np.cos(angle), np.sin(angle)
    # габариты повёрнутого эллипса: по ним берём ячейки, иначе углы фигуры срежутся
    half_x = np.hypot(rx * cos_a, rz * sin_a)
    half_z = np.hypot(rx * sin_a, rz * cos_a)
    c0, r0, c1, r1 = _bbox_cells(af, cx - half_x, cz - half_z, cx + half_x, cz + half_z)
    if c0 > c1 or r0 > r1:
        return None, 0, 0
    xs, zs = _cell_centers(af, c0, r0, c1, r1)
    dx = xs[None, :] - cx
    dz = zs[:, None] - cz
    along = (dx * cos_a + dz * sin_a) / rx        # координаты в осях самого эллипса
    across = (-dx * sin_a + dz * cos_a) / rz
    return (along * along + across * across) <= 1.0, c0, r0


def polygon_mask(af, points: list[tuple[float, float]]):
    """(маска, c0, r0) полигона по правилу чётности (even-odd). Лассо — тот же полигон.

    Растеризация построчная: для каждой строки ячеек ищем пересечения с рёбрами и
    определяем «внутри» по чётности пересечений слева (searchsorted по всей строке
    разом — цикл только по строкам bbox)."""
    if len(points) < 3:
        return None, 0, 0                        # линия, а не фигура
    px = np.array([p[0] for p in points], dtype=np.float64)
    pz = np.array([p[1] for p in points], dtype=np.float64)
    if (px.max() - px.min() < MIN_SHAPE_M) or (pz.max() - pz.min() < MIN_SHAPE_M):
        return None, 0, 0                        # схлопнутый контур — тоже линия
    c0, r0, c1, r1 = _bbox_cells(af, px.min(), pz.min(), px.max(), pz.max())
    if c0 > c1 or r0 > r1:
        return None, 0, 0
    xs, zs = _cell_centers(af, c0, r0, c1, r1)
    x1s, z1s = px, pz
    x2s, z2s = np.roll(px, -1), np.roll(pz, -1)  # рёбра, включая замыкающее
    mask = np.zeros((len(zs), len(xs)), dtype=bool)
    for i, z in enumerate(zs):
        crosses = (z1s > z) != (z2s > z)         # ребро пересекает строку
        if not crosses.any():
            continue
        a1z, a2z = z1s[crosses], z2s[crosses]
        a1x, a2x = x1s[crosses], x2s[crosses]
        t = (z - a1z) / (a2z - a1z)
        xints = np.sort(a1x + t * (a2x - a1x))
        mask[i] = (np.searchsorted(xints, xs) % 2) == 1
    return mask, c0, r0


def fill(af, key: str, mask: np.ndarray, c0: int, r0: int,
         erase: bool = False) -> Patch | None:
    """Применить маску к битплану. None — если ничего не изменилось."""
    if mask is None or not mask.any():
        return None
    arr, bit = plane_array(af, key)
    h, w = mask.shape
    sub = arr[r0:r0 + h, c0:c0 + w]
    before = sub.copy()
    bitmask = np.asarray(1 << bit, dtype=sub.dtype)
    if erase:
        sub[mask] &= ~bitmask
    else:
        sub[mask] |= bitmask
    if np.array_equal(before, sub):
        return None
    return Patch(key, c0, r0, before, sub.copy())


def fill_rect(af, key, x0, z0, x1, z1, erase=False) -> Patch | None:
    return fill(af, key, *rect_mask(af, x0, z0, x1, z1), erase=erase)


def fill_ellipse(af, key, x0, z0, x1, z1, angle: float = 0.0, erase=False) -> Patch | None:
    return fill(af, key, *ellipse_mask(af, x0, z0, x1, z1, angle), erase=erase)


def fill_polygon(af, key, points, erase=False) -> Patch | None:
    return fill(af, key, *polygon_mask(af, points), erase=erase)
