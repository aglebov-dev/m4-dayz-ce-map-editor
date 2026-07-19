"""Смоук нативного экстрактора (light.sat_extract): парсинг PBO + декод тайла.
Полную распаковку (десятки секунд) не гоняем — проверяем PBO/PAA/DXT/LZO на одном тайле.
Пропускается, если PBO игры недоступен."""
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

import numpy as np

from light.sat_extract import decode_dxt1, decode_paa, parse_pbo_tiles

PBO = r"D:\steam\steamapps\common\DayZ\Addons\worlds_chernarusplus_data.pbo"

# --- DXT1: один чёрный блок (c0=c1=0) -> чёрный 4×4 ---
blk = bytes([0, 0, 0, 0, 0, 0, 0, 0])
img = decode_dxt1(blk, 4, 4)
assert img.shape == (4, 4, 3) and img.max() == 0
# белый блок: c0=0xFFFF -> белый
blk = bytes([0xFF, 0xFF, 0, 0, 0, 0, 0, 0])
img = decode_dxt1(blk, 4, 4)
assert img[0, 0, 0] == 255 and img[0, 0, 2] == 255
print("DXT1: чёрный/белый блок декодируются верно")

# LZO проверяется на реальном тайле ниже (если мип сжат) — синтетику не гоняем:
# ручная сборка валидного LZO-потока хрупка и не нужна.
if not os.path.isfile(PBO):
    print("PBO игры не найден — пропуск проверки на реальных данных")
    print("OK")
    sys.exit(0)

# --- реальный PBO: разбор + декод центрального тайла ---
data, tiles = parse_pbo_tiles(PBO)
assert len(tiles) > 0
gw = max(t[0] for t in tiles) + 1
gh = max(t[1] for t in tiles) + 1
assert gw == 32 and gh == 32, (gw, gh)
off, size = next((o, s) for x, y, o, s in tiles if x == gw // 2 and y == gh // 2)
rgb = decode_paa(data[off:off + size])
assert rgb.shape == (512, 512, 3) and rgb.dtype == np.uint8
# спутник Черноруси — зелёно-тёмный, не мусор: разумный разброс, не однотонный
assert 10 < rgb.mean() < 120 and rgb.std() > 10
print(f"реальный PBO: сетка {gw}×{gh}, тайл {rgb.shape}, mean {rgb.mean():.0f} — ок")
print("OK")
