"""Типы CE (types.xml + ce-файлы из cfgeconomycore) и матчинг предметов к зданию.

Формула пригодности (доказана экспериментами, см. docs/knowledge.md):
category предмета ∈ категории контейнера ∧ tag (если задан) ∧
(usage-маска предмета пересекает эффективный usage здания; пустая — не ограничен) ∧
(value-маска аналогично). Поздние types-файлы переопределяют ранние по имени класса.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np

from core.groups import Buildings, GroupProto, read_user_aliases


@dataclass
class ItemType:
    name: str
    nominal: int
    min: int
    restock: int
    lifetime: int
    category: str | None
    usage_mask: int
    value_mask: int
    tags: frozenset[str]
    source: str          # файл, из которого пришло финальное определение


def ce_type_files(core_path: str) -> list[str]:
    """Относительные пути (folder/name) type-файлов, перечисленных в cfgeconomycore.xml.

    Это доп. типы кастомного сервера (`<ce folder="X"><file name="Y.xml" type="types"/>`).
    Нужны и для чтения, и для материализации — иначе редактор видит только db/types.xml."""
    out: list[str] = []
    try:
        root = ET.parse(core_path).getroot()
    except (ET.ParseError, OSError):
        return out
    for ce in root.findall(".//ce"):
        folder = ce.get("folder") or ""
        for f in ce.findall("file"):
            if f.get("type") == "types" and f.get("name"):
                out.append(f"{folder}/{f.get('name')}".strip("/").replace("\\", "/"))
    return out


def _types_files(mission_path: str) -> list[str]:
    files = []
    db = os.path.join(mission_path, "db", "types.xml")
    if os.path.isfile(db):
        files.append(db)
    core = os.path.join(mission_path, "cfgeconomycore.xml")
    if os.path.isfile(core):
        for rel in ce_type_files(core):
            p = os.path.join(mission_path, rel.replace("/", os.sep))
            if os.path.isfile(p):
                files.append(p)
    return files


def read_types(mission_path: str, usages: list[str], values: list[str]) -> dict[str, ItemType]:
    ualias, valias = read_user_aliases(mission_path, usages, values)
    out: dict[str, ItemType] = {}
    for path in _types_files(mission_path):
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        src = os.path.relpath(path, mission_path)
        for t in root.findall("type"):
            name = t.get("name")
            if not name:
                continue

            def num(tag: str) -> int:
                el = t.find(tag)
                try:
                    return int(el.text) if el is not None else 0
                except (TypeError, ValueError):
                    return 0

            umask = vmask = 0
            for u in t.findall("usage"):
                if u.get("name") in usages:
                    umask |= 1 << usages.index(u.get("name"))
                elif u.get("user"):
                    umask |= ualias.get(u.get("user"), 0)
            for v in t.findall("value"):
                if v.get("name") in values:
                    vmask |= 1 << values.index(v.get("name"))
                elif v.get("user"):
                    vmask |= valias.get(v.get("user"), 0)
            cat = t.find("category")
            out[name] = ItemType(
                name=name,
                nominal=num("nominal"),
                min=num("min"),
                restock=num("restock"),
                lifetime=num("lifetime"),
                category=cat.get("name") if cat is not None else None,
                usage_mask=umask,
                value_mask=vmask,
                tags=frozenset(x.get("name") for x in t.findall("tag")),
                source=src,
            )
    return out


def instances_for_item(t: ItemType, b: Buildings, eff_u: np.ndarray,
                       eff_v: np.ndarray) -> np.ndarray:
    """Обратный матчинг: глобальные индексы инстансов, где предмет может заспавниться.
    Та же формула, что items_for_building, векторизованная по инстансам."""
    if t.nominal <= 0 or t.category is None:
        return np.empty(0, dtype=np.int64)
    ok_group = {name: any(t.category in c.categories and (not t.tags or t.tags & c.tags)
                          for c in p.containers)
                for name, p in b.protos.items()}
    m = np.fromiter((ok_group.get(n, False) for n in b.names),
                    dtype=bool, count=len(b.names))
    if t.usage_mask:
        m &= (eff_u & np.uint32(t.usage_mask)) != 0
    if t.value_mask:
        m &= (eff_v & np.uint8(t.value_mask & 0xFF)) != 0
    return np.flatnonzero(m)


def items_for_building(types: dict[str, ItemType], proto: GroupProto,
                       eff_u: int, eff_v: int) -> list[ItemType]:
    """Предметы, которые могут заспавниться в здании (nominal > 0), по формуле."""
    conts = [(c.categories, c.tags) for c in proto.containers]
    out = []
    for t in types.values():
        if t.nominal <= 0 or t.category is None:
            continue
        if t.usage_mask and not t.usage_mask & eff_u:
            continue
        if t.value_mask and not t.value_mask & eff_v:
            continue
        for cats, tags in conts:
            if t.category in cats and (not t.tags or t.tags & tags):
                out.append(t)
                break
    out.sort(key=lambda t: (t.category or "", t.name.lower()))
    return out
