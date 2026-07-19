"""Генерация датасета footprint зданий из файлов игры (нативно, как распаковщик тайлов).

По каждому `structures*.pbo`: читаем `config.bin` (класс → модель, `core.config_bin`) и
индексируем `.p3d`; для каждого `Land_*`-класса берём bbox из ODOL-заголовка модели →
footprint (w×l, высота, смещение центра). Результат — `<world>.json` в формате
`core.building_index` (кладётся в appdata/buildings). Позиции/повороты берутся не отсюда, а
из mapgrouppos проекта, поэтому датасет — это чисто таблица «класс → габариты», общая для
всех миров.
"""
from __future__ import annotations

import glob
import json
import os
import struct

from core import config_bin, pbo


def _bbox(head: bytes) -> dict | None:
    """footprint из ODOL-заголовка .p3d: bbox модели (min/max), санити по viewDensity."""
    if len(head) < 12 or head[:4] != b"ODOL":
        return None
    lod_count = struct.unpack_from("<I", head, 8)[0]
    start = 12 + lod_count * 4                    # начало ModelInfo
    try:
        view_density = struct.unpack_from("<f", head, start + 44)[0]
        mn = struct.unpack_from("<3f", head, start + 48)
        mx = struct.unpack_from("<3f", head, start + 60)
    except struct.error:
        return None
    w, h, l = mx[0] - mn[0], mx[1] - mn[1], mx[2] - mn[2]
    if not (0 < w < 2000 and 0 < l < 2000 and 0 < h < 2000):
        return None
    if not (-200 < view_density <= 0.001):
        return None
    return {"w": round(w, 3), "l": round(l, 3), "h": round(h, 3),
            "ox": round((mn[0] + mx[0]) / 2, 3), "oz": round((mn[2] + mx[2]) / 2, 3)}


def structures_pbos(addons_dir: str) -> list[str]:
    return sorted(glob.glob(os.path.join(addons_dir, "structures*.pbo")))


def generate(game_dir: str, world: str, out_path: str, log=print) -> int:
    """Собрать footprint всех `Land_*`-классов из `<game>/Addons/structures*.pbo` → out_path.
    Возвращает число классов с footprint. UnpackError-подобных исключений не глотаем сверху —
    вызывающий решает, что делать (для нас это «дополнительно к тайлам», не критично)."""
    addons = os.path.join(game_dir, "Addons")
    pbos = structures_pbos(addons)
    if not pbos:
        raise FileNotFoundError(f"нет structures*.pbo в {addons}")

    models: dict[str, str] = {}
    parents: dict[str, str] = {}
    canon: dict[str, str] = {}
    p3d: dict[str, tuple[str, int, int]] = {}    # basename -> (pbo_path, offset, size)
    for path in pbos:
        try:
            data, entries, _prefix = pbo.read_pbo(path)
        except Exception as error:
            log(f"  пропуск {os.path.basename(path)}: {error}")
            continue
        cfg = pbo.read_entry(data, entries, "config.bin")
        if cfg:
            try:
                m, p, c = config_bin.parse(cfg)
                models.update(m); parents.update(p); canon.update(c)
            except Exception as error:
                log(f"  config {os.path.basename(path)}: {error}")
        for key, (off, size, method) in entries.items():
            if key.endswith(".p3d") and method == 0:
                p3d[os.path.basename(key)] = (path, off, size)

    classes = []
    for cls in sorted(c for c in models if c.startswith("land_")):
        model = config_bin.resolve_model(cls, models, parents)
        if not model:
            continue
        entry = p3d.get(os.path.basename(model.replace("\\", "/").lower()))
        if not entry:
            continue
        path, off, size = entry
        with open(path, "rb") as f:
            f.seek(off)
            head = f.read(min(size, 8192))
        footprint = _bbox(head)
        if footprint:
            classes.append({"name": canon.get(cls, cls), "footprint": footprint})

    dataset = {"map": world, "worldSize": 0, "source": "game-pbo",
               "classes": classes, "instances": []}
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, ensure_ascii=False)
    log(f"здания: {len(classes)} классов с footprint → {out_path}")
    return len(classes)
