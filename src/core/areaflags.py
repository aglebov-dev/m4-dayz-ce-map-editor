"""Ридер areaflags.map + флаги из cfglimitsdefinition.xml.

Формат ОДИН — версий v1/v2 НЕ существует (см. memory areaflags-format). Раскладка:
[header 24 байта] [usage: uint32/ячейку] [tier: байт/ячейку, либо ниббл при ≤4 values].
Грабли — docs/knowledge.md. Ключевое:
- порядок битов = порядок флагов в cfglimitsdefinition.xml ЭТОЙ карты, не хардкодить;
- row 0 = ЮГ;
- слой B (tier): байт/ячейку при 5 valueflags, ниббл при ≤4 (младший ниббл = чётная ячейка);
- «формат v2» (+5851 байт у боевого сервера) — это НЕ версия и НЕ другой формат: тот же файл,
  испорченный текстовой конвертацией CRLF (unix2dos: перед каждым 0x0A вставлен 0x0D).
  Снимается точно (_dos2unix); сохранение всегда пишет чистый файл.
"""
from __future__ import annotations

import os
import struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import numpy as np


def read_limits(mission_path: str) -> tuple[list[str], list[str]]:
    """(usage-флаги, value-флаги) в порядке их битов из cfglimitsdefinition.xml миссии."""
    p = os.path.join(mission_path, "cfglimitsdefinition.xml")
    root = ET.parse(p).getroot()
    usages = [u.get("name") for u in root.find("usageflags")]
    values = [v.get("name") for v in root.find("valueflags")]
    return usages, values


@dataclass
class AreaFlags:
    grid_x: int
    grid_y: int
    size_x: int          # метры
    size_y: int
    usages: list[str]
    values: list[str]
    usage: np.ndarray    # uint32[cells], битмаска usage-флагов (в памяти ВСЕГДА uint32)
    tier: np.ndarray     # uint8/uint16[cells], битмаска value-флагов
    repaired_crlf: int = 0   # >0: файл был испорчен unix2dos, убрано столько 0x0D
    # ширины НА ДИСКЕ (в памяти планы всегда шире): usage_bytes берётся из заголовка
    # (поле 5 = бит на ячейку, встречались 32 и 16), tier_bits — из числа valueflags:
    # ≤4 ниббл, ≤8 байт, ≤16 два байта. Сохранение возвращает исходные ширины.
    usage_bytes: int = 4
    tier_bits: int = 8
    # заголовок как есть (24 байта): 6-е поле = 0 во всех известных картах, назначение
    # неизвестно — при записи возвращаем его байт в байт, а не собираем заново
    header: np.ndarray | None = None
    source_path: str = ""
    source_mtime: float = 0.0

    @property
    def cells(self) -> int:
        return self.grid_x * self.grid_y

    @property
    def cell_size(self) -> float:
        return self.size_x / self.grid_x

    def plane(self, name: str) -> np.ndarray:
        """Битплан флага -> bool[grid_y, grid_x], row 0 = ЮГ."""
        if name in self.usages:
            a, bit = self.usage, self.usages.index(name)
        else:
            a, bit = self.tier, self.values.index(name)
        return ((a >> bit) & 1).astype(bool).reshape(self.grid_y, self.grid_x)

    def tier_grid(self) -> np.ndarray:
        """Битмаска тиров -> uint8[grid_y, grid_x], row 0 = ЮГ."""
        return self.tier.reshape(self.grid_y, self.grid_x)

    @property
    def usage_bits(self) -> int:
        """Сколько бит под usage в ячейке — столько флагов карта и способна хранить."""
        return self.usage_bytes * 8

    def unwritable_usages(self) -> list[str]:
        """usage-флаги, которым в ячейке НЕТ бита.

        Ширина ячейки фиксируется при генерации карты, а `cfglimitsdefinition.xml` живёт
        своей жизнью — флагов там бывает больше (DeerIsle: 22 при 16 битах, ванильный
        halloween.chernarusplus: 17 при 16). Такой флаг нельзя ни нарисовать, ни сохранить,
        поэтому кисть его не предлагает."""
        return self.usages[self.usage_bits:]


def _dos2unix(raw: np.ndarray) -> np.ndarray:
    """Убирает 0x0D, стоящие непосредственно перед 0x0A (обратное к unix2dos).
    Обратимо точно: unix2dos вставляет 0x0D перед КАЖДЫМ 0x0A, включая исходные пары."""
    drop = np.flatnonzero((raw[:-1] == 13) & (raw[1:] == 10))
    keep = np.ones(raw.size, dtype=bool)
    keep[drop] = False
    return raw[keep]


def widen_usage(af: AreaFlags, bits: int = 32) -> None:
    """Расширить ячейку usage до `bits` бит — чтобы стали доступны все объявленные флаги.

    Меняется только вместимость ячейки: номер бита у флага прежний, нарисованные зоны
    сохраняются один в один (`0x0041` -> `0x00000041`). Сам файл при сохранении будет
    ПЕРЕПИСАН с новым шагом, а не перечитан по-другому: правка одного поля заголовка без
    переписывания данных склеила бы соседние ячейки попарно — размер бы не сошёлся и
    `read_areaflags` такой файл не принял.

    Раскладка на выходе — та же, что у ванильных миссий с 32-битным usage
    (chernarusplus, enoch, sakhal), так что формат для игры не новый."""
    if bits not in (16, 32):
        raise ValueError(f"ширина {bits} не встречалась; бывают 16 и 32")
    if bits <= af.usage_bits:
        raise ValueError(f"ячейка уже {af.usage_bits} бит — сужать нельзя, данные потерялись бы")
    if af.header is None or af.header.size != 24:
        raise ValueError("нет исходного заголовка (24 байта)")
    header = bytearray(af.header.tobytes())
    struct.pack_into("<I", header, 16, bits)      # поле 5 = бит на ячейку usage
    af.header = np.frombuffer(bytes(header), dtype=np.uint8).copy()
    af.usage_bytes = bits // 8


def _tier_bits(values: list[str]) -> int:
    """Сколько бит на ячейку занимает слой value (tier). Ширина растёт по числу флагов:
    ≤4 — ниббл, ≤8 — байт, ≤16 — два байта (модовые карты: у DeerIsle 15 Tier-флагов)."""
    if len(values) <= 4:
        return 4
    if len(values) <= 8:
        return 8
    if len(values) <= 16:
        return 16
    raise ValueError(f"value-флагов {len(values)} — больше 16 не встречалось")


def _expand_nibbles(raw: np.ndarray, cells: int) -> np.ndarray:
    """Ниббл-слой B -> байт/ячейку. Младший ниббл = чётная ячейка."""
    t = np.empty(cells, dtype=np.uint8)
    t[0::2] = raw[: cells // 2] & 0x0F
    t[1::2] = (raw[: cells // 2] >> 4) & 0x0F
    return t


def _pack_nibbles(tier: np.ndarray) -> np.ndarray:
    """Обратное к _expand_nibbles: байт/ячейку -> ниббл-слой B."""
    return ((tier[0::2] & 0x0F) | ((tier[1::2] & 0x0F) << 4)).astype(np.uint8)


def read_areaflags(mission_path: str) -> AreaFlags:
    """Читает areaflags.map миссии. Файл с CRLF-порчей чинится на лету (точно).
    Неопознанный размер -> ValueError."""
    map_path = os.path.join(mission_path, "areaflags.map")
    usages, values = read_limits(mission_path)

    buf = np.fromfile(map_path, dtype=np.uint8)
    hdr = np.frombuffer(buf[:24].tobytes(), dtype=np.uint32)
    grid_x, grid_y, size_x, size_y, usage_bits = (int(v) for v in hdr[:5])
    cells = grid_x * grid_y
    ubytes = usage_bits // 8
    if ubytes not in (2, 4):
        raise ValueError(f"usage_bits={usage_bits}, ожидалось 16 или 32")
    # флагов может быть объявлено больше, чем влезает в ячейку (DeerIsle: 22 флага при
    # 16 битах) — читать это не мешает, а вот запись такой маски отобьёт writer.pack
    tier_bits = _tier_bits(values)
    nibble = tier_bits == 4
    b_size = cells * tier_bits // 8
    expected = 24 + cells * ubytes + b_size

    repaired = 0
    if buf.size != expected:
        fixed = _dos2unix(buf)
        if fixed.size != expected:
            raise ValueError(
                f"неизвестный размер areaflags.map: {buf.size:,} байт "
                f"(ожидалось {expected:,}; после снятия CRLF {fixed.size:,})")
        repaired = buf.size - fixed.size
        buf = fixed

    off_b = 24 + cells * ubytes
    # .copy(): frombuffer отдаёт массив только для чтения, а кисть (этап 11) пишет в него
    # usage в памяти всегда uint32 — иначе каждый потребитель считал бы ширину сам
    on_disk = np.uint32 if ubytes == 4 else np.uint16
    usage = np.frombuffer(buf[24:off_b].tobytes(), dtype=on_disk).astype(np.uint32)
    raw_b = buf[off_b:off_b + b_size]
    if nibble:
        tier = _expand_nibbles(raw_b, cells)
    elif tier_bits == 8:
        tier = raw_b.copy()
    else:
        tier = np.frombuffer(raw_b.tobytes(), dtype=np.uint16).copy()
    return AreaFlags(grid_x, grid_y, size_x, size_y, usages, values,
                     usage, tier, repaired_crlf=repaired,
                     usage_bytes=ubytes, tier_bits=tier_bits,
                     header=buf[:24].copy(), source_path=map_path,
                     source_mtime=os.path.getmtime(map_path))
