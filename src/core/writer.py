"""Запись areaflags.map: чистый v1, бэкап, атомарная замена, проверка после записи.

Этот файл читает движок игры — цена ошибки высокая, поэтому:
- пишем ВСЕГДА чистый v1 (без CRLF-порчи; если исходник был испорчен unix2dos,
  сохранение его чинит — см. docs/knowledge.md);
- заголовок возвращаем байт в байт (в нём есть поле, назначение которого неизвестно);
- сначала пишем во временный файл рядом и только потом os.replace — прерывание записи
  не оставит движку обрезанный файл;
- перед заменой делаем бэкап с меткой времени (прошлый бэкап не затирается);
- после записи файл ПЕРЕЧИТЫВАЕТСЯ и сверяется с памятью; разошлось — откат из бэкапа.
"""
from __future__ import annotations

import os
from datetime import datetime

import numpy as np

from core.areaflags import AreaFlags, _pack_nibbles, read_areaflags


class WriteError(Exception):
    """Запись невозможна или проверка после записи не сошлась."""


class FileChangedError(WriteError):
    """Файл на диске изменился с момента загрузки (кто-то переписал areaflags.map)."""


def pack(af: AreaFlags) -> np.ndarray:
    """AreaFlags -> байты чистого v1. Проверяет, что данные вообще представимы."""
    cells = af.cells
    nibble = len(af.values) <= 4
    if af.usage.size != cells or af.tier.size != cells:
        raise WriteError(f"размер данных не сходится с сеткой {af.grid_x}×{af.grid_y}")
    if nibble and int(af.tier.max(initial=0)) > 0x0F:
        raise WriteError("value-маска не влезает в ниббл (>4 бит) — файл был бы битым")
    header = af.header
    if header is None or header.size != 24:
        raise WriteError("нет исходного заголовка (24 байта)")
    b = _pack_nibbles(af.tier) if nibble else af.tier.astype(np.uint8)
    out = np.concatenate([
        header.astype(np.uint8),
        np.frombuffer(af.usage.astype("<u4").tobytes(), dtype=np.uint8),
        b,
    ])
    expected = 24 + cells * 4 + (cells // 2 if nibble else cells)
    if out.size != expected:
        raise WriteError(f"собрано {out.size:,} байт вместо {expected:,}")
    return out


def save_areaflags(af: AreaFlags, path: str = "", backup: bool = True,
                   force: bool = False, verify: bool = True) -> dict:
    """Пишет af в areaflags.map. Возвращает {'path', 'backup', 'bytes', 'crlf_removed'}.

    force=True — писать, даже если файл на диске изменился после загрузки."""
    path = path or af.source_path
    if not path:
        raise WriteError("не задан путь к areaflags.map")
    data = pack(af)                              # соберём ДО того, как трогать диск

    if os.path.exists(path) and not force and af.source_mtime:
        if os.path.getmtime(path) != af.source_mtime:
            raise FileChangedError(
                "файл на диске изменился после загрузки — перечитайте карту, "
                "иначе чужие правки будут затёрты")

    backup_path = ""
    if backup and os.path.exists(path):
        backup_path = _free_backup_path(path)
        _copy(path, backup_path)                 # копия, не перенос: оригинал на месте
                                                 # до самой замены

    tmp = f"{path}.tmp"
    try:
        data.tofile(tmp)
        os.replace(tmp, path)                    # атомарно: движок не увидит огрызок
    except Exception as e:
        _cleanup(tmp)
        raise WriteError(f"не удалось записать файл: {e}") from e

    if verify:                                   # перечитать и сверить с памятью
        try:
            back = read_areaflags(os.path.dirname(path))
            ok = (back.repaired_crlf == 0
                  and np.array_equal(back.usage, af.usage)
                  and np.array_equal(back.tier, af.tier)
                  and np.array_equal(back.header, af.header))
        except Exception as e:
            ok = False
            err = e
        else:
            err = None
        if not ok:
            if backup_path:                      # вернуть как было — файл рабочий
                _copy(backup_path, path)
            raise WriteError(
                f"проверка после записи не сошлась{f': {err}' if err else ''}"
                f"{'; файл восстановлен из бэкапа' if backup_path else ''}")

    af.source_path = path
    af.source_mtime = os.path.getmtime(path)
    crlf_removed = af.repaired_crlf
    af.repaired_crlf = 0                         # на диске теперь чистый v1
    return {"path": path, "backup": backup_path, "bytes": int(data.size),
            "crlf_removed": crlf_removed}


def _free_backup_path(path: str) -> str:
    """Свободное имя бэкапа с меткой времени. Два сохранения в одну секунду дают одну
    метку — тогда добавляем номер: старый бэкап дороже, чем красивое имя."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    p = f"{path}.{stamp}.bak"
    n = 2
    while os.path.exists(p):
        p = f"{path}.{stamp}-{n}.bak"
        n += 1
        if n > 1000:
            raise WriteError(f"не найти свободное имя для бэкапа рядом с {path}")
    return p


def _copy(src: str, dst: str):
    import shutil
    shutil.copy2(src, dst)


def _cleanup(p: str):
    try:
        os.remove(p)
    except OSError:
        pass
