"""Распаковка спутниковой подложки из файлов игры — НАТИВНО на Python.

Пользователь указывает папку игры; PBO берём из <game>/Addons/worlds_<world>_data.pbo
и разбираем встроенным экстрактором (light.sat_extract) в пирамиду тайлов core.tiles
в служебной папке приложения. Внешних зависимостей (dotnet и т.п.) не требуется.

Имя по шаблону работает только для ванильных карт. У модовых PBO зовётся как угодно
(у DeerIsle тайлы лежат в `data.pbo`), поэтому файл можно указать и напрямую —
`unpack_pbo`. Экстрактору имя безразлично: тайлы он ищет по содержимому, `layers\\S_*_lco`."""
from __future__ import annotations

import glob
import os

from core import pbo
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
    return unpack_pbo(pbo, world, world_size, log=log)


def has_tiles(path: str) -> bool:
    """Есть ли в PBO спутниковые тайлы. По заголовку, без чтения данных."""
    try:
        entries, _prefix = pbo.read_header(path)
    except Exception:
        return False
    return any(k.startswith("layers/s_") and "_lco" in k for k in entries)


def find_tile_pbos(addons_dir: str) -> list[str]:
    """Какие PBO папки содержат тайлы — имена у модов произвольные, ищем по содержимому."""
    return [p for p in sorted(glob.glob(os.path.join(addons_dir, "*.pbo"))) if has_tiles(p)]


#     префикс                          -> мир
#     deerisle\data                    -> deerisle
#     H2A\GreenCounty\data             -> greencounty   (H2A — пространство имён мода)
#     DZ\worlds\chernarusplus\data     -> chernarusplus
_PREFIX_TAIL = {"data", "ce", "world", "worlds", "layers"}


def world_name_from_pbo(pbo_path: str) -> str:
    """Имя мира по PBO: последний осмысленный компонент `prefix` из заголовка.

    Первый компонент не годится — у модов там бывает пространство имён студии, а не карта.
    Служебные хвосты (`data`, `ce`, …) отбрасываем. Нет префикса — берём имя файла."""
    try:
        _entries, prefix = pbo.read_header(pbo_path)
    except Exception:
        prefix = ""
    parts = [p for p in prefix.replace("/", "\\").split("\\") if p.strip()]
    while parts and parts[-1].strip().lower() in _PREFIX_TAIL:
        parts.pop()
    name = parts[-1].strip().lower() if parts else ""
    return name or os.path.splitext(os.path.basename(pbo_path))[0].lower()


def unpack_pbo(pbo_path: str, world: str, world_size: float, log=print) -> str:
    """То же, но PBO указан напрямую — для модовых карт, где шаблон имени не подходит.

    `world` тут только имя мира проекта: под ним пирамида ложится в кэш и по нему её
    потом находит подложка. `world_size=0` — миссии нет и размер неизвестен, экстрактор
    посчитает его сам по полотну."""
    if not os.path.isfile(pbo_path):
        raise UnpackError(f"нет файла PBO: {pbo_path}")
    out = out_tiles_dir(world)
    try:
        extract(pbo_path, out, float(world_size), world_name=world, log=log)
    except ValueError as e:
        # самая частая ошибка выбора: в папке мода десятки PBO, тайлы лежат в одном
        found = [p for p in find_tile_pbos(os.path.dirname(pbo_path)) if p != pbo_path]
        hint = ""
        if found:
            names = ", ".join(os.path.basename(p) for p in found)
            hint = f"\nТайлы в этой папке лежат здесь: {names}"
        raise UnpackError(f"распаковка не удалась: {e}{hint}") from e
    except Exception as e:
        raise UnpackError(f"распаковка не удалась: {e}") from e
    if not os.path.isfile(os.path.join(out, "meta.json")):
        raise UnpackError("пирамида (meta.json) не создана")
    return out
