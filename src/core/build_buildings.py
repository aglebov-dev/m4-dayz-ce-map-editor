"""Генерация датасета footprint зданий из файлов игры (нативно, как распаковщик тайлов).

По каждому `structures*.pbo`: читаем `config.bin` (класс → модель, `core.config_bin`) и
индексируем `.p3d`; для каждого `Land_*`-класса берём bbox из ODOL-заголовка модели →
footprint (w×l, высота, смещение центра).

Позиции/повороты берутся не отсюда, а из mapgrouppos проекта, поэтому датасет — чисто
таблица «класс → габариты», одинаково годная для любой карты. Отсюда две цели записи
(обе в формате `core.building_index`, обе в appdata/buildings):
- `<world>.json` — набор конкретной карты, перекрывает общий;
- `_shared.json` — общая библиотека, копится от каждой распаковки и читается для ЛЮБОГО
  мира. Туда классы только ДОБАВЛЯЮТСЯ: мод, переопределивший ванильный класс своей
  моделью, не должен менять габариты на чужих картах.
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


def all_pbos(addons_dir: str) -> list[str]:
    """Все PBO папки — для мода: имена там произвольные, зданий в `structures*` нет."""
    return sorted(glob.glob(os.path.join(addons_dir, "*.pbo")))


def collect_classes(pbos: list[str], log=print) -> list[dict]:
    """`класс → footprint` по списку PBO. Конфиги и модели складываются в общий индекс:
    класс из одного PBO может ссылаться на модель из другого (мод переопределяет ваниль).

    Читаем только заголовки и нужные записи: у мода в папке бывают десятки гигабайт, а нам
    от каждого PBO нужен `config.bin` и по 8 КБ ODOL-заголовка на модель."""
    models: dict[str, str] = {}
    parents: dict[str, str] = {}
    canon: dict[str, str] = {}
    p3d: dict[str, tuple[str, int, int]] = {}    # basename -> (pbo_path, offset, size)
    for path in pbos:
        try:
            entries, _prefix = pbo.read_header(path)
        except Exception as error:
            log(f"  пропуск {os.path.basename(path)}: {error}")
            continue
        cfg = pbo.read_entry_at(path, entries, "config.bin")
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
        # часть классов задаёт модель БЕЗ расширения (`…/container_1bo`), а индекс собран
        # по именам файлов — без нормализации такие классы молча терялись
        base = os.path.basename(model.replace("\\", "/").lower())
        entry = p3d.get(base if base.endswith(".p3d") else base + ".p3d")
        if not entry:
            continue
        model_pbo, off, size = entry
        with open(model_pbo, "rb") as f:
            f.seek(off)
            head = f.read(min(size, 8192))
        footprint = _bbox(head)
        if footprint:
            classes.append({"name": canon.get(cls, cls), "footprint": footprint,
                            "source": os.path.basename(model_pbo)})
    return classes


def merge_into(path: str, classes: list[dict], *, overwrite: bool, world: str = "") -> tuple[int, int]:
    """Долить классы в датасет `path` (создав его при необходимости). (добавлено, обновлено).

    `overwrite=False` — не трогать уже известные классы: так наполняется общая библиотека,
    где ваниль остаётся авторитетом, а мод, переопределивший ванильный класс своей моделью,
    не портит габариты на других картах (для своей карты его перекроет `<world>.json`).
    Прочие поля файла (`instances`, `worldSize`) сохраняются как есть."""
    data: dict = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}                            # битый файл перезаписываем, а не падаем
    known = {c["name"]: c for c in data.get("classes", []) if "name" in c}
    added = updated = 0
    for item in classes:
        old = known.get(item["name"])
        if old is None:
            known[item["name"]] = item
            added += 1
        elif overwrite and old.get("footprint") != item.get("footprint"):
            known[item["name"]] = item
            updated += 1
    data["map"] = data.get("map") or world
    data.setdefault("worldSize", 0)
    data.setdefault("instances", [])
    data["classes"] = sorted(known.values(), key=lambda c: c["name"])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    return added, updated


def generate(game_dir: str, world: str, out_path: str, shared_path: str = "",
             log=print) -> int:
    """Собрать footprint всех `Land_*`-классов из `<game>/Addons/structures*.pbo`.

    Кладёт их в `out_path` (датасет мира, свои классы важнее) и, если задан `shared_path`,
    доливает в общую библиотеку — оттуда габариты берутся для ЛЮБОЙ карты. Возвращает число
    собранных классов. Исключения не глотаем: вызывающий решает, критично ли это."""
    addons = os.path.join(game_dir, "Addons")
    pbos = structures_pbos(addons)
    if not pbos:
        raise FileNotFoundError(f"нет structures*.pbo в {addons}")

    return _build(pbos, world, out_path, shared_path, log)


def generate_from_addons(addons_dir: str, world: str, out_path: str, shared_path: str = "",
                         log=print) -> int:
    """То же для папки Addons мода: перебираем ВСЕ PBO, а не `structures*`.

    У мода здания раскиданы по своим архивам с произвольными именами (у DeerIsle это
    `classic_objects.pbo`, `militarycases.pbo`, `Skeleton.pbo`, `jmc_di_objects.pbo`…),
    так что фильтровать по имени нечем — читаем заголовки всех и берём те, где есть
    `config.bin` с `Land_*`-классами."""
    pbos = all_pbos(addons_dir)
    if not pbos:
        raise FileNotFoundError(f"нет PBO в {addons_dir}")
    return generate_from_pbos(pbos, world, out_path, shared_path, log)


def generate_from_pbos(pbos: list[str], world: str, out_path: str, shared_path: str = "",
                       shared_pbos: list[str] | None = None, log=print) -> int:
    """Сбор по готовому списку PBO — им пользуются обёртки выше.

    Порядок списка = приоритет конфигов: кладите ваниль первой, мод следом, тогда классы
    мода перекроют одноимённые ванильные, а наследование `Land_*` от ванильных родителей
    всё равно разрешится (индексы конфигов общие на весь список).

    `shared_pbos` — что считать авторитетом для общей библиотеки (по умолчанию весь список).
    Для модовой карты сюда передают ТОЛЬКО ванильные PBO: иначе мод, переопределивший
    ванильный класс, попадёт в общую библиотеку первым и разъедется на других картах."""
    if not pbos:
        raise FileNotFoundError("список PBO пуст")
    classes = collect_classes(pbos, log=log)
    added, updated = merge_into(out_path, classes, overwrite=True, world=world)
    log(f"здания: {len(classes)} классов с footprint → {out_path} "
        f"(+{added} новых, {updated} обновлено)")
    if shared_path:
        base = classes if shared_pbos is None else collect_classes(shared_pbos, log=log)
        shared_added, _ = merge_into(shared_path, base, overwrite=False)
        log(f"общая библиотека: +{shared_added} классов → {shared_path}")
    return len(classes)
