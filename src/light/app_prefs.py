"""Небольшое хранилище UI-настроек приложения: `appdata/app_prefs.json`.

Отдельно от `core.workspace.Settings` (та про workdir/подложки/цвета конкретной карты и
живёт единственным экземпляром в главном окне). Здесь — мелкие app-level настройки, к
которым удобно обращаться из любого места (напр. поля формы SFTP в приветственном окне),
без риска, что сохранение главного окна их затрёт."""
from __future__ import annotations

import json

from core.paths import paths


def _path():
    return paths.appdata / "app_prefs.json"


def load() -> dict:
    path = _path()
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save(data: dict) -> None:
    paths.ensure(paths.appdata)
    _path().write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get(key: str, default=None):
    return load().get(key, default)


def set(key: str, value) -> None:
    data = load()
    data[key] = value
    save(data)
