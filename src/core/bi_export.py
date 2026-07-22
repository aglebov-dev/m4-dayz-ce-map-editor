"""Экспорт в проект CE Tool (BI), вариант Б: слой-на-флаг.

Пишем в выбранную папку:
- areaflags.map (чистый v1) + cfglimitsdefinition.xml — то, что читает движок;
- layers/<usgFlg|valueFlg>_<name>.tga — 8bpp маска каждого флага (255 = флаг стоит);
- <world>.xml (<zg-config>) — проект CE Tool со списком слоёв и их масками.

Round-trip точный: каждый флаг = отдельный слой; деление Def/Paint из исходного проекта
не сохраняется (по варианту Б), зато стирание и точное совпадение работают."""
from __future__ import annotations

import os
import shutil

import numpy as np

from core.areaflags import AreaFlags
from core.ce_import import shift_usage_east
from core.writer import pack


def _write_tga_gray(path: str, plane_south0: np.ndarray):
    """8bpp raw TGA (тип 3), начало кадра — верхний левый (север сверху).
    plane_south0 — bool[grid_y, grid_x], row 0 = ЮГ; переворачиваем под TGA."""
    arr = np.ascontiguousarray(plane_south0[::-1])          # север сверху
    h, w = arr.shape
    data = (arr.astype(np.uint8) * 255)
    header = bytes([0, 0, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0,
                    w & 0xFF, (w >> 8) & 0xFF, h & 0xFF, (h >> 8) & 0xFF, 8, 0x20])
    with open(path, "wb") as f:
        f.write(header)
        f.write(data.tobytes())


def _color_argb(rgb) -> int:
    r, g, b = rgb
    return (0xFF << 24) | (r << 16) | (g << 8) | b


def export_project(af: AreaFlags, out_dir: str, cfglimits_src: str = "",
                   colors: dict | None = None, world: str = "world",
                   background_png: str = "") -> dict:
    """Экспортировать проект BI. Возвращает сводку {'map','layers','xml','background'}."""
    os.makedirs(out_dir, exist_ok=True)
    layers_dir = os.path.join(out_dir, "layers")
    os.makedirs(layers_dir, exist_ok=True)
    colors = colors or {}

    # 0) подложка одним файлом map.png (BI-редактор ссылается на неё в проекте)
    has_bg = bool(background_png and os.path.isfile(background_png))
    if has_bg:
        shutil.copy2(background_png, os.path.join(out_dir, "map.png"))

    # 1) areaflags.map (чистый v1)
    pack(af).tofile(os.path.join(out_dir, "areaflags.map"))

    # 2) cfglimitsdefinition.xml — берём актуальный (с добавленными/удалёнными флагами)
    if cfglimits_src and os.path.isfile(cfglimits_src):
        shutil.copy2(cfglimits_src, os.path.join(out_dir, "cfglimitsdefinition.xml"))

    # 3) TGA-слои по каждому флагу + записи проекта
    layer_xml = []
    n_layers = 0
    for name in af.values:
        plane = af.plane(name)
        fn = f"valueFlg_{name}"
        _write_tga_gray(os.path.join(layers_dir, f"{fn}.tga"), plane)
        bit = af.values.index(name)
        layer_xml.append(
            f'        <layer usage_flags="0" value_flags="{1 << bit}" '
            f'color="{_color_argb(colors.get(f"tier:{name}", (255, 255, 255)))}" '
            f'visible="1" name="{fn}"/>')
        n_layers += 1
    for name in af.usages:
        # usage пишем на колонку восточнее: компилятор BI при чтении сдвигает на запад
        # и вернёт исходный битплан (симметрично импорту, см. core.ce_import)
        plane = shift_usage_east(af.plane(name))
        fn = f"usgFlg_{name}"
        _write_tga_gray(os.path.join(layers_dir, f"{fn}.tga"), plane)
        bit = af.usages.index(name)
        layer_xml.append(
            f'        <layer usage_flags="{1 << bit}" value_flags="0" '
            f'color="{_color_argb(colors.get(f"usage:{name}", (255, 255, 255)))}" '
            f'visible="1" name="{fn}"/>')
        n_layers += 1

    # 4) проект <zg-config>
    usages = "\n".join(f'            <usage name="{n}"/>' for n in af.usages)
    values = "\n".join(f'            <value name="{n}"/>' for n in af.values)
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!--DayZ CE tool project file (экспорт CE Editor Light)-->
<zg-config>
    <global>
        <background file="map.png" rgba="16777215"/>
        <layer size="{af.grid_x}"/>
        <world size="{af.size_x}"/>
    </global>
    <areas>
        <usages>
{usages}
        </usages>
        <values>
{values}
        </values>
    </areas>
    <layers>
{chr(10).join(layer_xml)}
    </layers>
</zg-config>
"""
    xml_path = os.path.join(out_dir, f"{world}.xml")
    with open(xml_path, "w", encoding="utf-8") as f:
        f.write(xml)

    return {"map": os.path.join(out_dir, "areaflags.map"),
            "layers": n_layers, "xml": xml_path, "background": has_bg}
