"""Локализация: словари в assets/i18n/<lang>.json, подтягиваются по имени файла.
По умолчанию английский; выбранная локаль будет храниться в настройках (позже)."""
from __future__ import annotations

import json
import os

from core.paths import paths

DEFAULT_LANG = "en"
I18N_DIR = paths.i18n

_strings: dict[str, str] | None = None
_lang = DEFAULT_LANG


def available() -> list[str]:
    """Языки, для которых есть файл словаря."""
    if not os.path.isdir(I18N_DIR):
        return []
    return sorted(f[:-5] for f in os.listdir(I18N_DIR) if f.endswith(".json"))


def load(lang: str = DEFAULT_LANG) -> None:
    global _strings, _lang
    path = os.path.join(I18N_DIR, f"{lang}.json")
    try:
        _strings = json.load(open(path, encoding="utf-8"))
        _lang = lang
    except Exception:
        _strings = {}
        _lang = lang


def tr(key: str, **kw) -> str:
    """Строка по ключу; отсутствующий ключ возвращается как есть (виден в UI)."""
    if _strings is None:
        load(DEFAULT_LANG)
    s = _strings.get(key, key)
    return s.format(**kw) if kw else s
