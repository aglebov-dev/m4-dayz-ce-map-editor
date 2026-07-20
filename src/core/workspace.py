"""Рабочий каталог сервера: поиск карт (миссий) и их свойств."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


MISSION_MARKERS = ("cfglimitsdefinition.xml", "areaflags.map", "mapgroupproto.xml")


@dataclass
class Mission:
    name: str
    path: str
    world: str
    world_size: int
    has_areaflags: bool = False


def _looks_like_mission(path: str) -> bool:
    return any(os.path.isfile(os.path.join(path, m)) for m in MISSION_MARKERS)


def _world_size_from_areaflags(path: str) -> int | None:
    af = os.path.join(path, "areaflags.map")
    if not os.path.isfile(af):
        return None
    import struct
    with open(af, "rb") as f:
        hdr = f.read(24)
    if len(hdr) < 24:
        return None
    _, _, size_x, *_ = struct.unpack("<6I", hdr)
    return size_x or None


def _make_mission(path: str, name: str = "") -> Mission:
    """Mission из папки data/. `name` (из config проекта) задаёт имя миссии и мир —
    в плоской раскладке сама папка называется 'data', имя миссии хранится в config."""
    label = os.path.basename((name or path).rstrip("/\\")) or "mission"
    world = label.rsplit(".", 1)[-1].lower() if "." in label else label.lower()
    size = _world_size_from_areaflags(path) or 15360
    return Mission(
        name=label, path=path, world=world, world_size=size,
        has_areaflags=os.path.isfile(os.path.join(path, "areaflags.map")),
    )


def scan_workdir(root: str, mission_name: str = "") -> list[Mission]:
    """Миссия проекта лежит плоско в <root>/data; имя миссии — из config (`mission_name`).
    Вложенная раскладка `data/<миссия>/` и mission-в-корне больше НЕ поддерживаются."""
    data = os.path.join(root, "data")
    if _looks_like_mission(data):
        return [_make_mission(data, name=mission_name)]
    return []


class Settings:
    """settings.json в корне проекта: рабочий каталог, карта, подложки по картам."""

    def __init__(self, path: str):
        self.path = path
        self.data: dict = {"workdir": "", "last_mission": "", "backgrounds": {},
                           "lang": "en"}
        if os.path.isfile(path):
            try:
                self.data.update(json.load(open(path, encoding="utf-8")))
            except Exception:
                pass

    def save(self) -> None:
        json.dump(self.data, open(self.path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)

    @property
    def workdir(self) -> str:
        return self.data.get("workdir", "")

    @workdir.setter
    def workdir(self, v: str) -> None:
        self.data["workdir"] = v

    @property
    def cluster_mode(self) -> str:
        """Группировка зданий: 'merged' (единые кружки) | 'per-layer' (по слоям, v1)."""
        return self.data.get("cluster_mode", "merged")

    @property
    def lang(self) -> str:
        return self.data.get("lang", "en")

    @lang.setter
    def lang(self, v: str) -> None:
        self.data["lang"] = v

    @property
    def last_mission(self) -> str:
        return self.data.get("last_mission", "")

    @last_mission.setter
    def last_mission(self, v: str) -> None:
        self.data["last_mission"] = v

    def background_for(self, mission_name: str) -> str:
        return self.data.get("backgrounds", {}).get(mission_name, "")

    def set_background(self, mission_name: str, path: str) -> None:
        self.data.setdefault("backgrounds", {})[mission_name] = path

    def layer_color(self, mission_name: str, key: str) -> tuple[int, int, int] | None:
        """Пользовательский цвет слоя (key: tier:<имя>/usage:<имя>) или None."""
        c = self.data.get("layer_colors", {}).get(mission_name, {}).get(key)
        return tuple(c) if c else None

    def set_layer_color(self, mission_name: str, key: str, rgb: tuple[int, int, int]) -> None:
        self.data.setdefault("layer_colors", {}).setdefault(mission_name, {})[key] = list(rgb)
