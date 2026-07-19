"""Лутабельные группы (mapgroupproto) и их инстансы на карте (mapgrouppos).

Грабля №4 из knowledge.md: mapgrouppos.xml содержит ВСЕ объекты карты (включая деревья),
лутабельно только то, что описано в proto. Эффективные флаги инстанса — по доказанной формуле:
usage = usage группы ∪ usage ячейки; value = тир ячейки ∪ value группы.
Алиасы (<usage user="..."/>) резолвятся через cfglimitsdefinitionuser.xml.
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np


@dataclass
class Container:
    name: str
    lootmax: int
    categories: frozenset[str]
    tags: frozenset[str]
    points: int


@dataclass
class GroupProto:
    name: str
    usage_mask: int      # биты в порядке cfglimitsdefinition
    value_mask: int
    lootmax: int
    containers: list[Container]
    points: int          # число лут-точек (сумма по контейнерам)


@dataclass
class Buildings:
    protos: dict[str, GroupProto]
    names: list[str]     # имя группы каждого инстанса
    x: np.ndarray        # float32[n]
    z: np.ndarray
    yaw: np.ndarray      # float32[n] — истинный модельный yaw (град) из mapgrouppos


def read_user_aliases(mission_path: str, usages: list[str],
                      values: list[str]) -> tuple[dict[str, int], dict[str, int]]:
    """Алиас -> маска базовых флагов. Файла может не быть — тогда пусто."""
    p = os.path.join(mission_path, "cfglimitsdefinitionuser.xml")
    ualias: dict[str, int] = {}
    valias: dict[str, int] = {}
    if not os.path.isfile(p):
        return ualias, valias
    root = ET.parse(p).getroot()
    for u in root.findall("usageflags/user"):
        mask = 0
        for f in u.findall("usage"):
            if f.get("name") in usages:
                mask |= 1 << usages.index(f.get("name"))
        ualias[u.get("name")] = mask
    for v in root.findall("valueflags/user"):
        mask = 0
        for f in v.findall("value"):
            if f.get("name") in values:
                mask |= 1 << values.index(f.get("name"))
        valias[v.get("name")] = mask
    return ualias, valias


def read_buildings(mission_path: str, usages: list[str], values: list[str]) -> Buildings:
    ualias, valias = read_user_aliases(mission_path, usages, values)

    def flag_mask(el: ET.Element, tag: str, base: list[str], alias: dict[str, int]) -> int:
        mask = 0
        for f in el.findall(tag):
            name, user = f.get("name"), f.get("user")
            if name and name in base:
                mask |= 1 << base.index(name)
            elif user:
                mask |= alias.get(user, 0)
        return mask

    protos: dict[str, GroupProto] = {}
    proto_root = ET.parse(os.path.join(mission_path, "mapgroupproto.xml")).getroot()
    for g in proto_root.findall("group"):
        name = g.get("name")
        containers = [Container(
            name=c.get("name") or "",
            lootmax=int(c.get("lootmax") or 0),
            categories=frozenset(x.get("name") for x in c.findall("category")),
            tags=frozenset(x.get("name") for x in c.findall("tag")),
            points=len(c.findall("point")),
        ) for c in g.findall("container")]
        protos[name] = GroupProto(
            name=name,
            usage_mask=flag_mask(g, "usage", usages, ualias),
            value_mask=flag_mask(g, "value", values, valias),
            lootmax=int(g.get("lootmax") or 0),
            containers=containers,
            points=sum(c.points for c in containers),
        )

    names: list[str] = []
    xs: list[float] = []
    zs: list[float] = []
    yaws: list[float] = []
    pos_root = ET.parse(os.path.join(mission_path, "mapgrouppos.xml")).getroot()
    for g in pos_root.findall("group"):
        name = g.get("name")
        if name not in protos:                   # деревья и прочий не-лут
            continue
        p = g.get("pos").split()
        names.append(name)
        xs.append(float(p[0]))
        zs.append(float(p[2]))
        yaws.append(_instance_yaw(g))
    return Buildings(protos=protos, names=names,
                     x=np.array(xs, dtype=np.float32), z=np.array(zs, dtype=np.float32),
                     yaw=np.array(yaws, dtype=np.float32))


def _instance_yaw(g: ET.Element) -> float:
    """Истинный модельный yaw (град) инстанса из mapgrouppos. Формат BI/DayZ Editor:
    `rpy="roll pitch yaw"` (третье значение = yaw) и/или `a` (азимут), причём `a = 90 − yaw`.
    Берём yaw из rpy; если его нет — восстанавливаем из `a`; нет и его — 0."""
    rpy = g.get("rpy")
    if rpy:
        parts = rpy.split()
        if len(parts) == 3:
            return float(parts[2])
    a = g.get("a")
    if a is not None:
        return 90.0 - float(a)
    return 0.0
