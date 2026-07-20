"""Чтение PBO-архивов игры (нативно, без внешних утилит).

Достаточно для наших задач: перечислить записи и прочитать несжатые (config.bin, .p3d в
структурных PBO хранятся method=0). Формат: [version-header со свойствами] [таблица записей]
[данные подряд]. Смещение данных = конец таблицы + суммы размеров предыдущих записей."""
from __future__ import annotations

import struct

_VERS = 0x56657273          # method «Vers» — граница version-заголовка со свойствами


_HEADER_CHUNK = 16 * 1024 * 1024     # таблица записей живёт в начале файла


def read_pbo(path: str) -> tuple[bytes, dict, str]:
    """path → (data, entries, prefix). entries: `имя(lower, '/')` → (offset, size, method).
    prefix — свойство `prefix` из version-заголовка (база пути записей внутри PBO).

    Читает файл ЦЕЛИКОМ: годится для конфигов и структурных PBO, но не для модовых
    гигабайтников — для них `read_header` + `read_entry_at`."""
    data = open(path, "rb").read()
    entries, prefix = _parse_table(data, path)
    return data, entries, prefix


def read_header(path: str) -> tuple[dict, str]:
    """Таблица записей и prefix БЕЗ чтения данных — файл может весить гигабайты."""
    with open(path, "rb") as handle:
        head = handle.read(_HEADER_CHUNK)
    return _parse_table(head, path)


def _parse_table(data: bytes, path: str = "") -> tuple[dict, str]:
    """Разобрать таблицу записей: [version-header] [записи] [терминатор]."""
    pos = 0

    def read_z() -> str:
        nonlocal pos
        start = pos
        while data[pos] != 0:
            pos += 1
            if pos >= len(data):                     # прочитанного куска не хватило
                raise ValueError(f"таблица записей длиннее {len(data)} байт: {path}")
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
    return entries, prefix


def read_entry(data: bytes, entries: dict, name: str) -> bytes | None:
    """Байты записи по имени. None — нет записи или она сжата (нам сжатые не нужны)."""
    e = entries.get(name.replace("\\", "/").lower())
    if not e:
        return None
    off, size, method = e
    if method != 0:                                  # структуры/config хранятся несжатыми
        return None
    return data[off:off + size]


def read_entry_at(path: str, entries: dict, name: str, limit: int = 0) -> bytes | None:
    """То же, но читает запись из файла по смещению — без загрузки всего PBO в память.
    `limit` > 0 — взять только первые байты (нам от .p3d нужен лишь ODOL-заголовок)."""
    e = entries.get(name.replace("\\", "/").lower())
    if not e:
        return None
    off, size, method = e
    if method != 0:
        return None
    with open(path, "rb") as handle:
        handle.seek(off)
        return handle.read(min(size, limit) if limit else size)
