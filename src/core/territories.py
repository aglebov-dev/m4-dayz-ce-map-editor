"""Территории животных: круги из env/*_territories.xml (по cfgenvironment.xml).

Каждый файл — один слой; в нём <territory color=...> с кругами <zone x= z= r=>.
Цвет ARGB uint32 (как в territory color). Мир: x/z в метрах, z=0 = ЮГ."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

import numpy as np


@dataclass
class TerritoryLayer:
    name: str
    path: str
    color: tuple[int, int, int]
    x: np.ndarray = field(default_factory=lambda: np.empty(0))
    z: np.ndarray = field(default_factory=lambda: np.empty(0))
    r: np.ndarray = field(default_factory=lambda: np.empty(0))

    @property
    def count(self) -> int:
        return len(self.x)


def _argb_to_rgb(v: int) -> tuple[int, int, int]:
    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF


def _list_files(mission_path: str) -> list[str]:
    """Пути territory-файлов из cfgenvironment.xml (<territories><file path=.../>).
    Дубликаты (в ваниле hare указан дважды) убираем, порядок сохраняем."""
    cfg = os.path.join(mission_path, "cfgenvironment.xml")
    if not os.path.isfile(cfg):
        return []
    root = ET.parse(cfg).getroot()
    seen: set[str] = set()
    out: list[str] = []
    terr = root.find("territories")
    for f in (terr.findall("file") if terr is not None else []):
        p = f.get("path")
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def read_territories(mission_path: str) -> list[TerritoryLayer]:
    """Слои территорий миссии. Пустые/битые файлы пропускаются (не валят загрузку)."""
    layers: list[TerritoryLayer] = []
    for rel in _list_files(mission_path):
        path = os.path.join(mission_path, rel)
        if not os.path.isfile(path):
            continue
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError:
            continue
        xs, zs, rs = [], [], []
        color = (255, 140, 0)
        first = True
        for terr in root.findall("territory"):
            if first:
                c = terr.get("color")
                if c is not None:
                    color = _argb_to_rgb(int(c))
                first = False
            for zone in terr.findall("zone"):
                xs.append(float(zone.get("x", 0)))
                zs.append(float(zone.get("z", 0)))
                rs.append(float(zone.get("r", 0)))
        if not xs:
            continue
        name = os.path.splitext(os.path.basename(path))[0]
        name = name[:-len("_territories")] if name.endswith("_territories") else name
        layers.append(TerritoryLayer(
            name=name, path=path, color=color,
            x=np.array(xs), z=np.array(zs), r=np.array(rs)))
    return layers
