"""Связные зоны битплана (4-связность). Ран-ленгт по строкам + union-find по ранам —
чистый numpy+python, без scipy; на слоях Chernarus работает за доли секунды."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Zone:
    cells: int                       # ячеек в зоне
    bbox: tuple[int, int, int, int]  # col0, row0, col1, row1 (включительно; row 0 = ЮГ)
    centroid: tuple[float, float]    # (col, row), дробные


def find_zones(mask: np.ndarray, min_cells: int = 1) -> list[Zone]:
    """Зоны маски bool[rows, cols], отсортированы по убыванию площади."""
    rows, cols = mask.shape
    run_row: list[int] = []          # для каждого рана: строка
    run_s: list[int] = []            # начало (вкл.)
    run_e: list[int] = []            # конец (искл.)
    parent: list[int] = []

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    pad = np.zeros(cols + 2, dtype=np.int8)
    prev: list[int] = []             # индексы ранов предыдущей строки
    for r in range(rows):
        pad[1:-1] = mask[r]
        d = np.diff(pad)
        starts = np.flatnonzero(d == 1)
        ends = np.flatnonzero(d == -1)
        cur: list[int] = []
        pi = 0
        for s, e in zip(starts.tolist(), ends.tolist()):
            idx = len(parent)
            parent.append(idx)
            run_row.append(r)
            run_s.append(s)
            run_e.append(e)
            cur.append(idx)
            # 4-связность: пересечение по колонкам с ранами строки r-1
            while pi < len(prev) and run_e[prev[pi]] <= s:
                pi += 1
            pj = pi
            while pj < len(prev) and run_s[prev[pj]] < e:
                union(prev[pj], idx)
                pj += 1
            if pj > pi:
                pi = pj - 1          # последний пересёкшийся может задеть и следующий ран
        prev = cur

    # агрегация по корням
    acc: dict[int, list] = {}        # root -> [cells, sum_col, sum_row, c0, r0, c1, r1]
    for i in range(len(parent)):
        root = find(i)
        n = run_e[i] - run_s[i]
        sum_col = (run_s[i] + run_e[i] - 1) * n / 2.0
        a = acc.get(root)
        if a is None:
            acc[root] = [n, sum_col, run_row[i] * n,
                         run_s[i], run_row[i], run_e[i] - 1, run_row[i]]
        else:
            a[0] += n
            a[1] += sum_col
            a[2] += run_row[i] * n
            a[3] = min(a[3], run_s[i])
            a[5] = max(a[5], run_e[i] - 1)
            a[6] = run_row[i]        # строки идут по возрастанию
    zones = [Zone(cells=a[0], bbox=(a[3], a[4], a[5], a[6]),
                  centroid=(a[1] / a[0], a[2] / a[0]))
             for a in acc.values() if a[0] >= min_cells]
    zones.sort(key=lambda z: z.cells, reverse=True)
    return zones
