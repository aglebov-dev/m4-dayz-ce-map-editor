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
    usage: np.ndarray    # uint32[cells], битмаска usage-флагов
    tier: np.ndarray     # uint8[cells], битмаска value-флагов
    repaired_crlf: int = 0   # >0: файл был испорчен unix2dos, убрано столько 0x0D
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


def _dos2unix(raw: np.ndarray) -> np.ndarray:
    """Убирает 0x0D, стоящие непосредственно перед 0x0A (обратное к unix2dos).
    Обратимо точно: unix2dos вставляет 0x0D перед КАЖДЫМ 0x0A, включая исходные пары."""
    drop = np.flatnonzero((raw[:-1] == 13) & (raw[1:] == 10))
    keep = np.ones(raw.size, dtype=bool)
    keep[drop] = False
    return raw[keep]


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
    if ubytes != 4:
        raise ValueError(f"usage_bits={usage_bits}, ожидалось 32")

    nibble = len(values) <= 4
    b_size = cells // 2 if nibble else cells
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
    usage = np.frombuffer(buf[24:off_b].tobytes(), dtype=np.uint32).copy()
    raw_b = buf[off_b:off_b + b_size]
    tier = _expand_nibbles(raw_b, cells) if nibble else raw_b.copy()
    return AreaFlags(grid_x, grid_y, size_x, size_y, usages, values,
                     usage, tier, repaired_crlf=repaired,
                     header=buf[:24].copy(), source_path=map_path,
                     source_mtime=os.path.getmtime(map_path))
