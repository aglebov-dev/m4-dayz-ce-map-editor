"""Распаковка спутниковой подложки из файлов игры — НАТИВНО на Python.

Пользователь указывает папку игры; PBO берём из <game>/Addons/worlds_<world>_data.pbo
и разбираем встроенным экстрактором (light.sat_extract) в пирамиду тайлов core.tiles
в служебной папке приложения. Внешних зависимостей (dotnet и т.п.) не требуется."""
from __future__ import annotations

import os

from core.paths import paths
from light.sat_extract import extract


class UnpackError(Exception):
    pass


def out_tiles_dir(world: str) -> str:
    """Куда распаковывать пирамиду мира — в writable-кэш подложек приложения."""
    d = paths.tiles_cache / world
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def pbo_path(game_dir: str, world: str) -> str:
    return os.path.join(game_dir, "Addons", f"worlds_{world}_data.pbo")


def available() -> bool:
    """Нативный распаковщик доступен всегда (numpy+Pillow в зависимостях)."""
    return True


def unpack(game_dir: str, world: str, world_size: float, log=print) -> str:
    """Распаковать подложку мира из файлов игры. Возвращает путь мира в служебной папке.
    Долгая операция (десятки секунд). Ошибки — UnpackError с понятным текстом."""
    if not os.path.isdir(game_dir):
        raise UnpackError(f"нет папки игры: {game_dir}")
    pbo = pbo_path(game_dir, world)
    if not os.path.isfile(pbo):
        raise UnpackError(f"нет PBO мира: {pbo}\n(проверьте, что выбрана папка игры DayZ "
                          f"и мир «{world}» установлен)")
    out = out_tiles_dir(world)
    try:
        extract(pbo, out, float(world_size), world_name=world, log=log)
    except Exception as e:
        raise UnpackError(f"распаковка не удалась: {e}") from e
    if not os.path.isfile(os.path.join(out, "meta.json")):
        raise UnpackError("пирамида (meta.json) не создана")
    return out
