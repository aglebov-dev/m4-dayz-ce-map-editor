"""Импорт проекта CE Tool (BI) как редактируемой карты — пара к `core.bi_export`.

`bi_export` пишет areaflags.map → TGA-слой-на-флаг + <zg-config>. Здесь обратный путь:
проект CE Tool (XML + TGA-слои) собирается в `AreaFlags`, который ядро читает и правит
как обычную карту. Плюс генерируется `cfglimitsdefinition.xml` (списки флагов) — его
`core.areaflags.read_limits` требует рядом с картой.

Сдвиг usage (важно!): компилятор BI кладёт usage-битплан на 1 колонку ЗАПАДНЕЕ
нарисованного слоя (тиры — без сдвига). Это НЕ приблизительно: сверено с офиц. проектами
DayZ-Central-Economy (CETool/* → dayzOffline.*) — usage со сдвигом на запад совпадает с
боевым areaflags.map на 100% (chernarus/enoch/sakhal). Поэтому импорт воспроизводит сдвиг,
а `bi_export` — обратный (на восток), чтобы round-trip и экспорт были верны реальному BI.
Флаг слоя берётся из АТРИБУТА usage_flags/value_flags XML, не из имени: у Def-слоёв в
реальных проектах атрибут часто 0 (пустой вклад) — по имени вышло бы переокрашивание."""
from __future__ import annotations

import os
import struct

import numpy as np

from core.areaflags import AreaFlags
from core.ce_project import CeProject, layer_mask, read_project


class CeImportError(Exception):
    """Проект CE Tool нельзя представить в формате areaflags.map."""


# Формат ограничен разрядностью битпланов areaflags.map:
MAX_USAGES = 32          # usage — uint32/ячейку
MAX_VALUES = 8           # value(tier) — uint8/ячейку (при ≤4 — ниббл)


def shift_usage_west(plane: np.ndarray) -> np.ndarray:
    """Сдвиг usage на 1 колонку западнее (out[:, x] = in[:, x+1]), крайняя восточная
    колонка обнуляется (без wrap). Соответствие боевому areaflags при импорте BI: сверено —
    100% совпадение по usage (расхождения только в самой восточной колонке-кромке карты:
    у enoch там 385 ячеек, у chernarus/sakhal — 1; это предел, колонки x+1 за краем нет)."""
    out = np.zeros_like(plane)
    out[:, :-1] = plane[:, 1:]
    return out


def shift_usage_east(plane: np.ndarray) -> np.ndarray:
    """Обратный сдвиг (out[:, x] = in[:, x-1]) — для экспорта в BI, чтобы компилятор BI
    (сдвигающий на запад) вернул исходный usage."""
    out = np.zeros_like(plane)
    out[:, 1:] = plane[:, :-1]
    return out


def _make_header(grid_x: int, grid_y: int, size_x: int, size_y: int) -> np.ndarray:
    """24-байтный заголовок v1: 6 uint32. Поле usage_bits=32 (usage — uint32), 6-е поле=0
    (назначение неизвестно; во всех известных картах ноль)."""
    return np.frombuffer(
        struct.pack("<6I", grid_x, grid_y, size_x, size_y, 32, 0),
        dtype=np.uint8,
    ).copy()


def build_areaflags(project: CeProject) -> AreaFlags:
    """Проект CE Tool → AreaFlags. usage/value планы собираются OR-ом масок слоёв:
    каждый слой закрашивает свои флаги (usage_mask/value_mask) в нарисованных ячейках."""
    if len(project.usages) > MAX_USAGES:
        raise CeImportError(
            f"usage-флагов {len(project.usages)} > {MAX_USAGES} — не влезает в uint32")
    if len(project.values) > MAX_VALUES:
        raise CeImportError(
            f"value-флагов {len(project.values)} > {MAX_VALUES} — не влезает в uint8")

    grid = project.layer_size
    world = project.world_size
    cells = grid * grid
    usage = np.zeros(cells, dtype=np.uint32)
    tier = np.zeros(cells, dtype=np.uint8)

    for layer in project.layers:
        if not layer.usage_mask and not layer.value_mask:
            continue
        try:
            mask = layer_mask(project, layer.name).reshape(-1)   # bool[cells], row0=юг
        except (OSError, ValueError) as error:
            raise CeImportError(
                f"слой «{layer.name}»: не прочитать TGA ({error})") from error
        if mask.size != cells:
            raise CeImportError(
                f"слой «{layer.name}»: размер {mask.size} не совпадает с сеткой {cells}")
        if layer.usage_mask:
            usage[mask] |= np.uint32(layer.usage_mask)
        if layer.value_mask:
            if layer.value_mask > 0xFF:
                raise CeImportError(
                    f"слой «{layer.name}»: value-маска {layer.value_mask} шире 8 бит")
            tier[mask] |= np.uint8(layer.value_mask)

    # usage сдвигается на колонку западнее (соответствие боевому areaflags); тир — как есть
    usage = shift_usage_west(usage.reshape(grid, grid)).reshape(-1)

    return AreaFlags(
        grid_x=grid, grid_y=grid, size_x=world, size_y=world,
        usages=list(project.usages), values=list(project.values),
        usage=usage, tier=tier,
        header=_make_header(grid, grid, world, world))


def build_cfglimits_xml(usages: list[str], values: list[str]) -> str:
    """`cfglimitsdefinition.xml` из списков флагов (обратное к `read_limits`).
    categories/tags пустые — проект CE Tool их не содержит, ридеру карты они не нужны."""
    usage_rows = "\n".join(f'        <usage name="{name}"/>' for name in usages)
    value_rows = "\n".join(f'        <value name="{name}"/>' for name in values)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        "<lists>\n"
        "    <categories/>\n"
        "    <tags/>\n"
        "    <usageflags>\n"
        f"{usage_rows}\n"
        "    </usageflags>\n"
        "    <valueflags>\n"
        f"{value_rows}\n"
        "    </valueflags>\n"
        "</lists>\n"
    )


def import_ce_project(folder: str) -> tuple[AreaFlags, str]:
    """Прочитать проект CE Tool из папки и собрать (AreaFlags, cfglimits-XML).
    Материализация в проект приложения — на стороне вызывающего (слой light)."""
    project = read_project(folder)               # ValueError, если нет <zg-config>
    areaflags = build_areaflags(project)
    cfglimits = build_cfglimits_xml(project.usages, project.values)
    return areaflags, cfglimits


def write_mission(areaflags: AreaFlags, cfglimits_xml: str, mission_dir: str) -> str:
    """Записать areaflags.map + cfglimitsdefinition.xml в папку миссии. Возвращает путь."""
    from core.writer import pack

    os.makedirs(mission_dir, exist_ok=True)
    pack(areaflags).tofile(os.path.join(mission_dir, "areaflags.map"))
    with open(os.path.join(mission_dir, "cfglimitsdefinition.xml"), "w",
              encoding="utf-8") as file:
        file.write(cfglimits_xml)
    return mission_dir
