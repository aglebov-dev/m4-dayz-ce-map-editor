"""Импорт проекта CE Tool (Bohemia): XML-проект + TGA-слои.

Только ЧТЕНИЕ (экспорт обратно — отдельное решение, см. PLAN этап 13). Даёт:
- сравнение слоёв проекта с боевым areaflags;
- воду/сушу из water-fresh.tga (источник, которого не хватало инспектору в этапе 4).

Грабли (docs/knowledge.md):
- TGA у CE Tool: RLE-пакеты ПЕРЕСЕКАЮТ границы строк — PIL падает, декодер свой;
- TGA: строка 0 = СЕВЕР (desc bit5), у нас row 0 = ЮГ — переворачиваем;
- компилятор BI кладёт usage на 1 колонку ЗАПАДНЕЕ нарисованного (тиры — без сдвига):
  слой TGA и битплан в файле не совпадают буквально, при сравнении это учитываем."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np


@dataclass
class ProjectLayer:
    name: str
    usage_mask: int
    value_mask: int
    color: tuple[int, int, int]
    visible: bool

    @property
    def tga(self) -> str:
        return f"{self.name}.tga"


@dataclass
class CeProject:
    path: str
    layer_size: int
    world_size: int
    background: str
    usages: list[str]
    values: list[str]
    layers: list[ProjectLayer]

    def layer(self, name: str) -> ProjectLayer | None:
        return next((l for l in self.layers if l.name == name), None)


def _argb_to_rgb(v: int) -> tuple[int, int, int]:
    return (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF


def find_project_xml(folder: str) -> str | None:
    """Файл проекта в папке: XML с корнем <zg-config>."""
    for f in sorted(os.listdir(folder)):
        if not f.lower().endswith(".xml"):
            continue
        try:
            if ET.parse(os.path.join(folder, f)).getroot().tag == "zg-config":
                return os.path.join(folder, f)
        except ET.ParseError:
            continue
    return None


def read_project(folder: str) -> CeProject:
    """Читает проект CE Tool из папки. Без файла проекта — ValueError."""
    xml = find_project_xml(folder)
    if not xml:
        raise ValueError("в папке нет файла проекта CE Tool (<zg-config>)")
    root = ET.parse(xml).getroot()
    g = root.find("global")
    layer_size = int(g.find("layer").get("size")) if g is not None else 4096
    world_size = int(g.find("world").get("size")) if g is not None else 15360
    bg = ""
    if g is not None and g.find("background") is not None:
        bg = g.find("background").get("file", "")
    areas = root.find("areas")
    usages = [u.get("name") for u in areas.find("usages")] if areas is not None else []
    values = [v.get("name") for v in areas.find("values")] if areas is not None else []
    layers: list[ProjectLayer] = []
    for lay in root.find("layers") or []:
        layers.append(ProjectLayer(
            name=lay.get("name"),
            usage_mask=int(lay.get("usage_flags", 0)),
            value_mask=int(lay.get("value_flags", 0)),
            color=_argb_to_rgb(int(lay.get("color", 0))),
            visible=lay.get("visible", "0") == "1"))
    return CeProject(os.path.abspath(folder), layer_size, world_size, bg,
                     usages, values, layers)


def read_tga_gray(path: str) -> np.ndarray:
    """8bpp TGA (тип 3 raw или 11 RLE) -> uint8[h, w], строка 0 = как в файле (север).
    Свой декодер: RLE-пакеты пересекают границы строк, PIL это не берёт."""
    b = np.fromfile(path, dtype=np.uint8)
    id_len, img_type = int(b[0]), int(b[2])
    w = int(b[12]) | (int(b[13]) << 8)
    h = int(b[14]) | (int(b[15]) << 8)
    bpp = int(b[16])
    if bpp != 8:
        raise ValueError(f"ожидался 8bpp TGA, получен {bpp}")
    p = 18 + id_len
    if img_type == 3:
        out = b[p:p + w * h].astype(np.uint8)
    elif img_type == 11:
        out = np.empty(w * h, dtype=np.uint8)
        o = 0
        while o < out.size:
            pk = int(b[p]); p += 1
            cnt = (pk & 0x7F) + 1
            if pk & 0x80:
                out[o:o + cnt] = b[p]; p += 1
            else:
                out[o:o + cnt] = b[p:p + cnt]; p += cnt
            o += cnt
    else:
        raise ValueError(f"неподдерживаемый тип TGA: {img_type}")
    return out.reshape(h, w)


def layer_mask(project: CeProject, name: str) -> np.ndarray:
    """Слой проекта как bool[grid, grid], row 0 = ЮГ (перевёрнут под нашу модель).
    TGA-пиксель != 0 = закрашено."""
    arr = read_tga_gray(os.path.join(project.path, "layers", f"{name}.tga"))
    mask = arr != 0
    return mask[::-1]


def water_mask(project: CeProject) -> np.ndarray | None:
    """Вода из water-fresh.tga: bool[grid, grid], True = вода, row 0 = ЮГ.
    None — если слоя нет в проекте."""
    path = os.path.join(project.path, "layers", "water-fresh.tga")
    if not os.path.isfile(path):
        return None
    return read_tga_gray(path)[::-1] != 0
