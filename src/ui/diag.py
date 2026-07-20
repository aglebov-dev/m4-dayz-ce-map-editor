"""Диагностика обработчиков доков. Активна ТОЛЬКО при env `M4_DIAG=1` — иначе `trace`
возвращает функцию как есть (нулевые накладные расходы), а `log` ничего не делает.

Зачем: нативный abort Qt при перетаскивании доков не даёт ни ассерта, ни Python-трейса.
Оборачиваем каждый наш обработчик сигналов дока — пишем ENTER/exit в `appdata/dock_diag.log`
(строковая буферизация → каждая строка на диске до следующего вызова Qt). Последняя строка
`ENTER <handler>` без парного ` exit` = обработчик, внутри которого процесс умер."""
from __future__ import annotations

import functools
import os
from datetime import datetime

from core.paths import paths

ENABLED = bool(os.environ.get("M4_DIAG"))
_fh = None


def _file():
    global _fh
    if _fh is None:
        paths.ensure(paths.appdata)
        _fh = open(paths.appdata / "dock_diag.log", "a", encoding="utf-8", buffering=1)
    return _fh


def log(msg: str) -> None:
    if not ENABLED:
        return
    try:
        _file().write(f"{datetime.now():%H:%M:%S.%f} {msg}\n")
    except Exception:
        pass


def _first_objname(args) -> str:
    for x in args[1:]:
        getter = getattr(x, "objectName", None)
        if callable(getter):
            try:
                return getter()
            except Exception:
                return ""
    return ""


def trace(fn):
    """Декоратор: логировать вход/выход обработчика (только при M4_DIAG)."""
    if not ENABLED:
        return fn

    @functools.wraps(fn)
    def wrap(*a, **kw):
        name = getattr(fn, "__qualname__", fn.__name__)
        arg = _first_objname(a)
        log(f"ENTER {name} {arg}")
        try:
            r = fn(*a, **kw)
        except BaseException as e:
            log(f" RAISE {name} {arg}: {e!r}")
            raise
        log(f" exit  {name} {arg}")
        return r

    return wrap
