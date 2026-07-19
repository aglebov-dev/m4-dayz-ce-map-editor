"""Экспорт: JSON-сводка карты, CSV по зонам слоя, PNG-оверлеи.

Наследник исследовательского tools/af_export.py, но без его хардкода: имена флагов и
порядок битов берутся из cfglimitsdefinition миссии, «формат v2» не поминается (это была
CRLF-порча, см. docs/knowledge.md)."""
from __future__ import annotations

import csv
import io
import json

import numpy as np

from core.stats import Region, map_stats
from core.zones import Zone


def summary_dict(af, region: Region | None = None, buildings=None,
                 source: str = "") -> dict:
    """JSON-сводка: мета, площади по каждому флагу, покрытие. Регион — необязателен."""
    bx = buildings.x if buildings is not None else None
    bz = buildings.z if buildings is not None else None
    st = map_stats(af, region, bx, bz)
    scope = {"kind": "map"} if region is None else {
        "kind": "region",
        "cells": {"col0": region[0], "row0": region[1],
                  "col1": region[2], "row1": region[3]},
        "world_m": {"x0": region[0] * af.cell_size, "z0": region[1] * af.cell_size,
                    "x1": (region[2] + 1) * af.cell_size,
                    "z1": (region[3] + 1) * af.cell_size},
    }
    out = {
        "meta": {
            "source": source,
            "grid": [af.grid_x, af.grid_y],
            "world_size_m": [af.size_x, af.size_y],
            "cell_size_m": af.cell_size,
            "row0": "south (z=0)",
            "flag_names": {"usage": list(af.usages), "value": list(af.values)},
            "repaired_crlf_bytes": af.repaired_crlf,
        },
        "scope": scope,
        "totals": {
            "cells": st.cells,
            "area_km2": round(st.area_km2, 3),
            "buildings": st.buildings,
            "cells_with_any_usage": st.any_usage_cells,
            "cells_with_any_tier": st.any_tier_cells,
        },
        "flags": [
            {"key": f.key, "name": f.name, "cells": f.cells,
             "area_km2": round(f.area_km2, 3), "pct_of_scope": round(f.pct, 3)}
            for f in st.flags
        ],
    }
    return out


def summary_json(af, region: Region | None = None, buildings=None,
                 source: str = "") -> str:
    return json.dumps(summary_dict(af, region, buildings, source),
                      ensure_ascii=False, indent=1)


def zones_csv(zones: list[Zone], cell_size: float, layer: str) -> str:
    """CSV по зонам слоя: номер как в панели «Зоны», площадь, центр, bbox (метры)."""
    buf = io.StringIO()
    wr = csv.writer(buf, lineterminator="\n")
    wr.writerow(["layer", "zone", "cells", "area_ha", "center_x", "center_z",
                 "bbox_x0", "bbox_z0", "bbox_x1", "bbox_z1"])
    for i, z in enumerate(zones, 1):
        wr.writerow([
            layer, i, z.cells, round(z.cells * cell_size * cell_size / 10_000, 2),
            round((z.centroid[0] + 0.5) * cell_size, 1),
            round((z.centroid[1] + 0.5) * cell_size, 1),
            round(z.bbox[0] * cell_size, 1), round(z.bbox[1] * cell_size, 1),
            round((z.bbox[2] + 1) * cell_size, 1), round((z.bbox[3] + 1) * cell_size, 1),
        ])
    return buf.getvalue()


def mask_rgba(mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """bool-маска (row 0 = ЮГ) -> RGBA сплошным цветом, север сверху, вне маски прозрачно.
    Общая для оверлеев слоя, патчей кисти и экспорта PNG — цвет и переворот в одном месте."""
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[mask] = (*color, 255)
    return np.ascontiguousarray(rgba[::-1])


def flag_rgba(af, name: str, color: tuple[int, int, int]) -> np.ndarray:
    """RGBA-массив оверлея флага (север сверху) — для сохранения в PNG."""
    return mask_rgba(af.plane(name), color)
