"""Де-рапификатор бинарного config.bin (формат «raP») — ровно настолько, чтобы достать
`class → model`. Игра бинаризует config.cpp в config.bin внутри PBO, поэтому текстом его не
прочитать. Формат: заголовок `\\0raP`, затем дерево классов; каждый класс — родитель,
число записей и записи (класс/значение/массив) со смещениями на тела вложенных классов.

Нужны только строковые значения `model=...` и цепочка наследования (модель может прийти от
базового класса). Остальные типы записей корректно пропускаем, чтобы не сбить указатель."""
from __future__ import annotations

import struct


def parse(data: bytes) -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    """config.bin → (models, parents, canon). Ключи — имена классов в НИЖНЕМ регистре;
    `models[c]` — путь модели, `parents[c]` — родитель (lower), `canon[c]` — исходный регистр
    имени класса (для датасета: имена должны совпасть с `<group name>` в mapgrouppos)."""
    if data[:4] != b"\x00raP":
        raise ValueError("не rapified config (нет '\\0raP')")
    models: dict[str, str] = {}
    parents: dict[str, str] = {}
    canon: dict[str, str] = {}

    def asciiz(pos: int) -> tuple[str, int]:
        s = pos
        while data[pos] != 0:
            pos += 1
        return data[s:pos].decode("ascii", "replace"), pos + 1

    def compressed_uint(pos: int) -> tuple[int, int]:
        val = shift = 0
        while True:
            b = data[pos]; pos += 1
            val |= (b & 0x7F) << shift
            if not (b & 0x80):
                return val, pos
            shift += 7

    def skip_array(pos: int) -> int:
        n, pos = compressed_uint(pos)
        for _ in range(n):
            t = data[pos]; pos += 1
            if t == 0:
                _, pos = asciiz(pos)
            elif t in (1, 2):
                pos += 4
            elif t == 3:
                pos = skip_array(pos)
            else:
                pos += 4
        return pos

    def parse_body(pos: int, cls: str) -> None:
        parent, pos = asciiz(pos)
        if cls:
            parents[cls.lower()] = parent.lower()
            canon[cls.lower()] = cls
        n, pos = compressed_uint(pos)
        subclasses: list[tuple[str, int]] = []
        for _ in range(n):
            etype = data[pos]; pos += 1
            if etype == 0:
                name, pos = asciiz(pos)
                body_off = struct.unpack_from("<I", data, pos)[0]; pos += 4
                subclasses.append((name, body_off))
            elif etype == 1:
                subtype = data[pos]; pos += 1
                name, pos = asciiz(pos)
                if subtype == 0:
                    val, pos = asciiz(pos)
                    if cls and name.lower() == "model":
                        models[cls.lower()] = val
                else:
                    pos += 4
            elif etype == 2:
                _, pos = asciiz(pos)
                pos = skip_array(pos)
            elif etype in (3, 4, 5):
                _, pos = asciiz(pos)
            else:
                raise ValueError(f"неизвестный тип записи {etype}")
        for name, body_off in subclasses:
            parse_body(body_off, name)

    parse_body(16, "")
    return models, parents, canon


def resolve_model(cls: str, models: dict, parents: dict, seen: set | None = None) -> str | None:
    """Модель класса: своя или унаследованная от родителя. None — если модели нет."""
    seen = seen if seen is not None else set()
    c = cls.lower()
    if c in seen:
        return None
    seen.add(c)
    if c in models:
        return models[c]
    parent = parents.get(c)
    return resolve_model(parent, models, parents, seen) if parent else None
