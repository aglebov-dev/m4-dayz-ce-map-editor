"""Добавление новых usage/value-флагов в карту (для редактора).

Бит нового флага = его позиция в списке. Массивы уже широкие (usage uint32, tier uint8),
поэтому добавление имени НЕ меняет данные — только регистрирует бит. Ёмкость:
usage ≤ 32, value ≤ 8. Переход value 4→5 меняет раскладку слоя B (ниббл→байт) — это
штатно, writer пакует по текущему числу value."""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET

import numpy as np

from core.areaflags import AreaFlags

MAX_USAGE = 32
MAX_VALUE = 8


class FlagError(Exception):
    pass


def _valid_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise FlagError("пустое имя флага")
    if not all(c.isalnum() or c in "_-" for c in name):
        raise FlagError("имя флага: только буквы, цифры, _ и -")
    return name


def add_usage(af: AreaFlags, name: str) -> int:
    """Добавляет usage-флаг, возвращает его бит. Дубликат/переполнение — FlagError."""
    name = _valid_name(name)
    if name in af.usages:
        raise FlagError(f"usage-флаг '{name}' уже есть")
    if len(af.usages) >= MAX_USAGE:
        raise FlagError(f"достигнут предел usage-флагов ({MAX_USAGE})")
    af.usages.append(name)
    return len(af.usages) - 1


def add_value(af: AreaFlags, name: str) -> int:
    name = _valid_name(name)
    if name in af.values:
        raise FlagError(f"value-флаг '{name}' уже есть")
    if len(af.values) >= MAX_VALUE:
        raise FlagError(f"достигнут предел value-флагов ({MAX_VALUE})")
    af.values.append(name)
    return len(af.values) - 1


def _drop_bit(arr: np.ndarray, bit: int, width_mask: int):
    """Удалить бит `bit` из каждого элемента: биты выше сдвигаются вниз на 1.
    Возвращает массив того же dtype."""
    dtype = arr.dtype
    a = arr.astype(np.uint64)
    low_mask = np.uint64((1 << bit) - 1)
    keep_low = a & low_mask
    high = (a >> np.uint64(1)) & np.uint64(width_mask & ~((1 << bit) - 1))
    return (keep_low | high).astype(dtype)


def remove_usage(af: AreaFlags, name: str) -> int:
    """Удалить usage-флаг и его бит из данных (биты выше сдвигаются). Возвращает
    число ячеек, где флаг стоял (для предупреждения). Нет флага — FlagError."""
    if name not in af.usages:
        raise FlagError(f"нет usage-флага '{name}'")
    bit = af.usages.index(name)
    cells = int(np.count_nonzero(af.usage & np.uint32(1 << bit)))
    af.usage = _drop_bit(af.usage, bit, 0xFFFFFFFF)
    af.usages.pop(bit)
    return cells


def remove_value(af: AreaFlags, name: str) -> int:
    if name not in af.values:
        raise FlagError(f"нет value-флага '{name}'")
    bit = af.values.index(name)
    # маску строим по dtype слоя: у карт с >8 value-флагов он uint16, и np.uint8(1<<8)
    # там просто переполнится
    mask = af.tier.dtype.type(1 << bit)
    cells = int(np.count_nonzero(af.tier & mask))
    af.tier = _drop_bit(af.tier, bit, int(np.iinfo(af.tier.dtype).max))
    af.values.pop(bit)
    return cells


def write_cfglimits(mission_dir: str, af: AreaFlags):
    """Переписать cfglimitsdefinition.xml текущими usage/value (сохранив прочее).
    Порядок = порядок битов; движок и наш ридер берут биты отсюда."""
    path = os.path.join(mission_dir, "cfglimitsdefinition.xml")
    tree = ET.parse(path)
    root = tree.getroot()
    _replace_list(root, "usageflags", "usage", af.usages)
    _replace_list(root, "valueflags", "value", af.values)
    ET.indent(tree, space="    ")
    tree.write(path, encoding="UTF-8", xml_declaration=True)


def _replace_list(root, container_tag: str, item_tag: str, names: list[str]):
    cont = root.find(container_tag)
    if cont is None:
        cont = ET.SubElement(root, container_tag)
    for child in list(cont):
        cont.remove(child)
    for n in names:
        ET.SubElement(cont, item_tag, {"name": n})
