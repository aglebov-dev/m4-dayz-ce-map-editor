"""Нативная (Python) распаковка спутниковой подложки — порт ExtractSatMap.cs.

worlds_<world>_data.pbo → layers/S_XXX_YYY_lco.paa (DXT1/DXT5, мип с LZO) → склейка →
пирамида тайлов core.tiles: <out>/{z}/{x}_{y}.jpg + meta.json. Без внешних зависимостей
кроме numpy+Pillow (нативно внутри приложения)."""
from __future__ import annotations

import json
import os
import struct

import numpy as np
from PIL import Image


# ---------- PBO ----------

def parse_pbo_tiles(path: str):
    """Список спутниковых тайлов PBO: (x, y, offset, size). Заодно data_start."""
    with open(path, "rb") as f:
        data = f.read()
    pos = 0

    def read_z():
        nonlocal pos
        start = pos
        while data[pos] != 0:
            pos += 1
        s = data[start:pos].decode("ascii", "replace")
        pos += 1
        return s

    entries = []
    while True:
        name = read_z()
        method = struct.unpack_from("<I", data, pos)[0]; pos += 4
        pos += 12                                   # 3×uint32
        size = struct.unpack_from("<I", data, pos)[0]; pos += 4
        if name == "" and method == 0x56657273:     # заголовок версии
            while read_z() != "":
                read_z()
            continue
        if name == "":
            break
        entries.append((name, size))

    data_start = pos
    tiles = []
    off = data_start
    for name, size in entries:
        low = name.lower()
        stem = os.path.splitext(os.path.basename(name))[0]
        if low.startswith("layers\\s_") and stem.lower().endswith("_lco"):
            parts = stem.split("_")                 # S_XXX_YYY_lco
            tiles.append((int(parts[1]), int(parts[2]), off, size))
        off += size
    return data, tiles


# ---------- LZO1X ----------

def lzo1x_decompress(src: bytes, dst_len: int) -> bytes:
    """Порт minilzo lzo1x_decompress (структура goto сохранена состоянием)."""
    dst = bytearray(dst_len)
    ip = 0
    op = 0
    t = 0
    if src[ip] > 17:
        t = src[ip] - 17; ip += 1
        if t < 4:
            for _ in range(t):
                dst[op] = src[ip]; op += 1; ip += 1
            t = src[ip]; ip += 1
            state = "match"
        else:
            for _ in range(t):
                dst[op] = src[ip]; op += 1; ip += 1
            state = "first"
    else:
        state = "begin"

    while True:
        if state == "begin":
            t = src[ip]; ip += 1
            if t >= 16:
                state = "match"; continue
            if t == 0:
                while src[ip] == 0:
                    t += 255; ip += 1
                t += 15 + src[ip]; ip += 1
            t += 3
            for _ in range(t):
                dst[op] = src[ip]; op += 1; ip += 1
            state = "first"; continue

        if state == "first":
            t = src[ip]; ip += 1
            if t >= 16:
                state = "match"; continue
            m = op - 1 - 0x0800 - (t >> 2) - (src[ip] << 2); ip += 1
            dst[op] = dst[m]; op += 1; m += 1
            dst[op] = dst[m]; op += 1; m += 1
            dst[op] = dst[m]; op += 1
            t = src[ip - 2] & 3
            if t == 0:
                state = "begin"; continue
            for _ in range(t):
                dst[op] = src[ip]; op += 1; ip += 1
            t = src[ip]; ip += 1
            state = "match"; continue

        # state == "match"
        if t >= 64:
            m = op - 1 - ((t >> 2) & 7) - (src[ip] << 3); ip += 1
            t = (t >> 5) - 1
        elif t >= 32:
            t &= 31
            if t == 0:
                while src[ip] == 0:
                    t += 255; ip += 1
                t += 31 + src[ip]; ip += 1
            m = op - 1 - ((src[ip] | (src[ip + 1] << 8)) >> 2); ip += 2
        elif t >= 16:
            m = op - ((t & 8) << 11)
            t &= 7
            if t == 0:
                while src[ip] == 0:
                    t += 255; ip += 1
                t += 7 + src[ip]; ip += 1
            m -= (src[ip] | (src[ip + 1] << 8)) >> 2; ip += 2
            if m == op:
                break                               # конец потока
            m -= 0x4000
        else:
            m = op - 1 - (t >> 2) - (src[ip] << 2); ip += 1
            dst[op] = dst[m]; op += 1; m += 1
            dst[op] = dst[m]; op += 1
            t = src[ip - 2] & 3
            if t == 0:
                state = "begin"; continue
            for _ in range(t):
                dst[op] = src[ip]; op += 1; ip += 1
            t = src[ip]; ip += 1
            continue                                # остаёмся в match

        t += 2                                      # копия матча (может перекрываться)
        for _ in range(t):
            dst[op] = dst[m]; op += 1; m += 1
        t = src[ip - 2] & 3
        if t == 0:
            state = "begin"; continue
        for _ in range(t):
            dst[op] = src[ip]; op += 1; ip += 1
        t = src[ip]; ip += 1
        # остаёмся в match
    return bytes(dst)


# ---------- PAA + DXT (векторно) ----------

def _expand565(c: np.ndarray):
    r = ((c >> 11) & 31) * 255 // 31
    g = ((c >> 5) & 63) * 255 // 63
    b = (c & 31) * 255 // 31
    return r.astype(np.uint8), g.astype(np.uint8), b.astype(np.uint8)


def decode_dxt1(blocks: bytes, width: int, height: int) -> np.ndarray:
    """DXT1 -> RGB (H, W, 3), numpy-векторно по блокам 4×4."""
    bx, by = width // 4, height // 4
    b = np.frombuffer(blocks, dtype=np.uint8)[: bx * by * 8].reshape(by, bx, 8)
    c0 = b[:, :, 0].astype(np.uint16) | (b[:, :, 1].astype(np.uint16) << 8)
    c1 = b[:, :, 2].astype(np.uint16) | (b[:, :, 3].astype(np.uint16) << 8)
    r0, g0, bl0 = _expand565(c0); r1, g1, bl1 = _expand565(c1)
    pal = np.zeros((by, bx, 4, 3), dtype=np.uint8)
    pal[:, :, 0] = np.stack([r0, g0, bl0], -1)
    pal[:, :, 1] = np.stack([r1, g1, bl1], -1)
    gt = (c0 > c1)[..., None]
    p2 = np.where(gt, (2 * pal[:, :, 0].astype(np.uint16) + pal[:, :, 1]) // 3,
                  (pal[:, :, 0].astype(np.uint16) + pal[:, :, 1]) // 2).astype(np.uint8)
    p3 = np.where(gt, (pal[:, :, 0].astype(np.uint16) + 2 * pal[:, :, 1]) // 3,
                  0).astype(np.uint8)
    pal[:, :, 2] = p2
    pal[:, :, 3] = p3
    idx = (b[:, :, 4].astype(np.uint32) | (b[:, :, 5].astype(np.uint32) << 8)
           | (b[:, :, 6].astype(np.uint32) << 16) | (b[:, :, 7].astype(np.uint32) << 24))
    out = np.zeros((by, 4, bx, 4, 3), dtype=np.uint8)
    for py in range(4):
        for px in range(4):
            sel = (idx >> np.uint32(2 * (py * 4 + px))) & np.uint32(3)
            picked = np.take_along_axis(pal, sel[:, :, None, None], axis=2)[:, :, 0]
            out[:, py, :, px] = picked
    return out.reshape(by * 4, bx * 4, 3)


def decode_dxt5(blocks: bytes, width: int, height: int) -> np.ndarray:
    """DXT5 -> RGB (альфу игнорируем): берём цветовую половину каждого 16-байтного блока."""
    b = np.frombuffer(blocks, dtype=np.uint8)
    n = b.size // 16
    color = b[: n * 16].reshape(n, 16)[:, 8:].reshape(-1)
    return decode_dxt1(color.tobytes(), width, height)


def decode_paa(data: bytes) -> np.ndarray:
    """PAA (0xFF01 DXT1 / 0xFF05 DXT5) -> RGB (H, W, 3)."""
    pos = 0
    ptype = struct.unpack_from("<H", data, pos)[0]; pos += 2
    if ptype not in (0xFF01, 0xFF05):
        raise ValueError(f"неподдерживаемый PAA: 0x{ptype:04X}")
    while True:                                     # TAGG'и
        marker = data[pos:pos + 4]
        if marker != b"GGAT":
            break
        pos += 8
        length = struct.unpack_from("<I", data, pos)[0]; pos += 4
        pos += length
    pal_len = struct.unpack_from("<H", data, pos)[0]; pos += 2
    pos += pal_len * 3
    width = struct.unpack_from("<H", data, pos)[0]; pos += 2
    height = struct.unpack_from("<H", data, pos)[0]; pos += 2
    lzo = (width & 0x8000) != 0
    width &= 0x7FFF
    b0, b1, b2 = data[pos], data[pos + 1], data[pos + 2]; pos += 3
    mip_size = b0 | (b1 << 8) | (b2 << 16)
    mip = data[pos:pos + mip_size]
    block_bytes = 8 if ptype == 0xFF01 else 16
    expected = width // 4 * (height // 4) * block_bytes
    if lzo:
        mip = lzo1x_decompress(mip, expected)
    if ptype == 0xFF01:
        return decode_dxt1(mip, width, height)
    return decode_dxt5(mip, width, height)


# ---------- склейка + пирамида ----------

def _detect_overlap(left: np.ndarray, right: np.ndarray) -> int:
    """Перекрытие соседних тайлов: правый край левого ≈ левый край правого.

    Перебираем до половины тайла: у ванильных карт перекрытие мелкое, у модовых бывает
    крупное (DeerIsle — 128 px при тайле 512). Слишком короткий перебор возвращает 0, и
    тайлы кладутся с шагом во всю ширину — по карте идёт двоение на каждом стыке.
    При равном совпадении берём ШИРОКОЕ: на однородной воде совпадает любая ширина, а
    настоящее перекрытие даёт нулевую разницу и на текстуре."""
    h, w, _ = left.shape
    best, best_diff = 0, 1e18
    li = left.astype(np.int32); ri = right.astype(np.int32)
    for cand in range(1, w // 2 + 1):
        l = li[::7, w - cand:w, :3]
        r = ri[::7, 0:cand, :3]
        diff = np.abs(l - r).sum() / (l.size or 1)
        if diff <= best_diff:
            best_diff, best = diff, cand
    return best if best_diff < 8 else 0


def estimate_world_size(full_size: int, overlap: float) -> int:
    """Прикинуть размер мира по полотну, когда взять его неоткуда (нет миссии).

    Спутник идёт 1 px/м, а поле вокруг мира — половина перекрытия с каждой стороны, так что
    `полотно - перекрытие` уже почти ответ; остаётся хвост сетки тайлов за дальним краем.
    Округляем к кратному 256 — размеры миров кратны ему: chernarus 15360 и enoch 12800
    попадают точно, DeerIsle 16512 садится на 16384."""
    return int(round((full_size - overlap) / 256.0)) * 256


def extract(pbo_path: str, out_dir: str, world_size: float, world_name: str = "",
            log=print) -> str:
    """Распаковать PBO в пирамиду тайлов. Возвращает out_dir.

    `world_size=0` — размер мира неизвестен (карту смотрят без миссии): считаем его из
    полотна. На сами тайлы это не влияет, они режутся из пикселей; размер задаёт только
    привязку к метрам в meta.json."""
    data, tiles = parse_pbo_tiles(pbo_path)
    if not tiles:
        raise ValueError("в PBO нет спутниковых тайлов layers/S_*_lco")
    gw = max(t[0] for t in tiles) + 1
    gh = max(t[1] for t in tiles) + 1
    log(f"тайлов {len(tiles)}, сетка {gw}×{gh}")

    def tile_rgb(x, y):
        off, size = next((o, s) for tx, ty, o, s in tiles if tx == x and ty == y)
        return decode_paa(data[off:off + size])

    center = tile_rgb(gw // 2, gh // 2)
    tw, th = center.shape[1], center.shape[0]
    overlap = _detect_overlap(center, tile_rgb(gw // 2 + 1, gh // 2))
    step = tw - overlap
    full_size = step * (gw - 1) + tw
    log(f"тайл {tw}×{th}, перекрытие {overlap}px, полотно {full_size}×{full_size}")

    full = np.zeros((full_size, full_size, 3), dtype=np.uint8)
    by_pos = {(x, y): (o, s) for x, y, o, s in tiles}
    for (x, y), (off, size) in by_pos.items():
        rgb = decode_paa(data[off:off + size])
        px, py = x * step, y * step
        full[py:py + rgb.shape[0], px:px + rgb.shape[1]] = rgb[:, :, :3]

    # НОРМАЛИЗАЦИЯ к 1 px/м: редактор и TileMeta считают подложку в 1 px/м, а спутник
    # бывает и плотнее. Разрешение берём как отношение полотна к миру, округляя до
    # «круглого» значения: поле вокруг мира — это единицы процентов, оно не должно
    # утаскивать масштаб. Выводить масштаб из перекрытия НЕЛЬЗЯ: `полотно - перекрытие`
    # равно миру только там, где поле равно перекрытию (ваниль). У DeerIsle поле 128 px
    # при перекрытии 128, и такая формула давала 1.008 px/м — картинку ужимало на 0.8%,
    # то есть на юго-востоке карты здания уезжали на сотню метров.
    if not world_size:
        world_size = float(estimate_world_size(full_size, overlap))
        log(f"размер мира не задан — оценка по полотну: {world_size:.0f} м")
    ppm_raw = full_size / world_size
    ppm = min((0.25, 0.5, 1.0, 2.0, 4.0), key=lambda c: abs(c - ppm_raw))
    img = Image.fromarray(full)
    if abs(ppm - 1.0) > 1e-3:
        final = int(round(full_size / ppm))
        img = img.resize((final, final))
        full_size = final
        overlap = overlap / ppm
        log(f"нормализация 1 px/м: {ppm_raw:.3f} px/м → полотно {final}×{final}")
    # Поле вокруг мира = половина перекрытия: спутник выходит за террейн на полтайла
    # стыка с каждой стороны. Считать его как (полотно - мир)/2 нельзя — полотно кратно
    # шагу тайла и с дальнего края торчит лишнее (DeerIsle: 43 тайла = 16640 px при мире
    # 16384 + 128, то есть 192 px хвоста), от чего подложка съезжает на десятки метров.
    margin = overlap / 2.0
    tail = full_size - world_size - overlap          # хвост за дальним краем мира
    if tail < -1:
        log(f"внимание: полотно {full_size} меньше мира {world_size:.0f} м с полем")
    elif tail > 1:
        log(f"полотно шире мира на {tail:.0f} px — хвост сетки тайлов за дальним краем")

    os.makedirs(out_dir, exist_ok=True)
    out_tile = 256
    max_zoom = int(np.ceil(np.log2(full_size / out_tile)))
    img.resize((1024, 1024)).save(os.path.join(out_dir, "preview.jpg"), quality=85)
    # map.png — единая подложка для BI-редактора (CE Tool: <background file="map.png">).
    # Кап 4096: 15392² png был бы огромным, а фон в BI такого разрешения не требует.
    map_size = min(full_size, 4096)
    (img if full_size == map_size else img.resize((map_size, map_size))) \
        .save(os.path.join(out_dir, "map.png"))

    level = img
    for z in range(max_zoom, -1, -1):
        per = int(np.ceil(level.width / out_tile))
        zdir = os.path.join(out_dir, str(z))
        os.makedirs(zdir, exist_ok=True)
        for ty in range(per):
            for tx in range(per):
                box = (tx * out_tile, ty * out_tile,
                       min((tx + 1) * out_tile, level.width),
                       min((ty + 1) * out_tile, level.height))
                level.crop(box).save(os.path.join(zdir, f"{tx}_{ty}.jpg"), quality=85)
        log(f"уровень {z}: {per}×{per}")
        if z == 0:
            break
        level = level.resize(((level.width + 1) // 2, (level.height + 1) // 2))

    meta = {
        "name": world_name or os.path.basename(out_dir),
        "tileSize": out_tile, "maxZoom": max_zoom,
        "width": full_size, "height": full_size, "worldSize": world_size,
        "margin": margin, "pixelsPerMeter": 1.0,
    }
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    log(f"готово: {out_dir}")
    return out_dir
