"""Чтение PBO-архивов игры (нативно, без внешних утилит).

Достаточно для наших задач: перечислить записи и прочитать несжатые (config.bin, .p3d в
структурных PBO хранятся method=0). Формат: [version-header со свойствами] [таблица записей]
[данные подряд]. Смещение данных = конец таблицы + суммы размеров предыдущих записей."""
from __future__ import annotations

import struct

_VERS = 0x56657273          # method «Vers» — граница version-заголовка со свойствами


def read_pbo(path: str) -> tuple[bytes, dict, str]:
    """path → (data, entries, prefix). entries: `имя(lower, '/')` → (offset, size, method).
    prefix — свойство `prefix` из version-заголовка (база пути записей внутри PBO)."""
    data = open(path, "rb").read()
    pos = 0

    def read_z() -> str:
        nonlocal pos
        start = pos
        while data[pos] != 0:
            pos += 1
        s = data[start:pos].decode("ascii", "replace")
        pos += 1
        return s

    prefix = ""
    raw: list[tuple[str, int, int]] = []
    while True:
        name = read_z()
        method = struct.unpack_from("<I", data, pos)[0]; pos += 4
        pos += 12                                    # originalSize, reserved, timestamp
        size = struct.unpack_from("<I", data, pos)[0]; pos += 4
        if name == "" and method == _VERS:           # заголовок: свойства name\0value\0…
            while True:
                key = read_z()
                if key == "":
                    break
                value = read_z()
                if key.lower() == "prefix":
                    prefix = value
            continue
        if name == "":                               # пустая запись = конец таблицы
            break
        raw.append((name, method, size))

    off = pos
    entries: dict[str, tuple[int, int, int]] = {}
    for name, method, size in raw:
        entries[name.replace("\\", "/").lower()] = (off, size, method)
        off += size
    return data, entries, prefix


def read_entry(data: bytes, entries: dict, name: str) -> bytes | None:
    """Байты записи по имени. None — нет записи или она сжата (нам сжатые не нужны)."""
    e = entries.get(name.replace("\\", "/").lower())
    if not e:
        return None
    off, size, method = e
    if method != 0:                                  # структуры/config хранятся несжатыми
        return None
    return data[off:off + size]
