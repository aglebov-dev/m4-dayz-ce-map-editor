"""Рабочий каталог сервера: поиск карт (миссий) и их свойств."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


MISSION_MARKERS = ("cfglimitsdefinition.xml", "areaflags.map", "mapgroupproto.xml")


@dataclass
class Mission:
    name: str            # имя папки, напр. dayzOffline.chernarusplus
    path: str            # абсолютный путь
    world: str           # мир: суффикс после последней точки (chernarusplus)
    world_size: int      # метры, из заголовка areaflags.map (или 15360 по умолчанию)
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


def _make_mission(path: str) -> Mission:
    name = os.path.basename(os.path.normpath(path))
    world = name.rsplit(".", 1)[-1].lower() if "." in name else name.lower()
    size = _world_size_from_areaflags(path) or 15360
    return Mission(
        name=name, path=path, world=world, world_size=size,
        has_areaflags=os.path.isfile(os.path.join(path, "areaflags.map")),
    )


def scan_workdir(root: str) -> list[Mission]:
    """Ищет карты: <root>/mpmissions/*, затем <root>/* как миссии, затем сам root."""
    found: list[Mission] = []
    mp = os.path.join(root, "data")
    if os.path.isdir(mp):
        for d in sorted(os.listdir(mp)):
            p = os.path.join(mp, d)
            if os.path.isdir(p) and _looks_like_mission(p):
                found.append(_make_mission(p))
    if not found and os.path.isdir(root):
        for d in sorted(os.listdir(root)):
            p = os.path.join(root, d)
            if os.path.isdir(p) and _looks_like_mission(p):
                found.append(_make_mission(p))
    if not found and _looks_like_mission(root):
        found.append(_make_mission(root))
    return found


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
