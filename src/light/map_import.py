"""Импорт карты из файлов игры: тайлы подложки + датасет зданий, одной операцией.

Раньше это жило в панели подложки при создании проекта, и распаковка была привязана к
миссии: мир брался из неё. На деле ни тайлам, ни зданиям миссия не нужна — тайлы ищутся в
PBO по содержимому, здания собираются из конфигов игры и мода. Поэтому логика вынесена
сюда, а панель проекта только ВЫБИРАЕТ уже распакованную пирамиду.

Без Qt: вызывается и из вкладки приветствия, и из скриптов."""
from __future__ import annotations

import os

from core import build_buildings
from core.building_index import SHARED
from core.paths import paths
from light import tiles_unpack


def game_dir_from(mod_addons: str) -> str:
    """Папка игры по пути к папке Addons мода: мод лежит в `<game>/!Workshop/@Мод/Addons`,
    иначе игра бы его не загрузила. Пусто — если структура другая (мод скопирован в сторону)."""
    head = os.path.abspath(mod_addons)
    while True:
        head, tail = os.path.split(head)
        if not tail or not head:
            return ""
        if tail.lower().startswith("!workshop"):
            return head


def buildings_pbos(addons: str, game_dir: str = "") -> tuple[list[str], list[str]]:
    """(ванильные PBO, модовые PBO) для сбора моделей.

    Ваниль идёт первой: классы мода перекроют одноимённые ванильные, а наследование от
    ванильных родителей всё равно разрешится. Если `addons` — папка самой игры, модовых нет."""
    addons = os.path.abspath(addons)
    game_dir = game_dir or game_dir_from(addons)
    vanilla_addons = os.path.join(game_dir, "Addons") if game_dir else ""
    if not game_dir and os.path.basename(addons).lower() == "addons":
        vanilla_addons = addons                  # выбрали саму игру, а не мод
    vanilla = build_buildings.structures_pbos(vanilla_addons) if vanilla_addons else []
    mod = [] if os.path.normcase(addons) == os.path.normcase(vanilla_addons) \
        else build_buildings.all_pbos(addons)
    return vanilla, mod


def import_map(pbo_path: str, world: str, world_size: float = 0, log=print) -> dict:
    """Распаковать подложку из `pbo_path` и собрать здания из соседних PBO.

    `world_size=0` — миссии нет, экстрактор оценит размер по полотну. Здания не критичны:
    их сбой не отменяет уже распакованную подложку. Возвращает
    {'tiles': путь, 'classes': сколько классов с footprint, 'buildings_error': текст|''}."""
    tiles = tiles_unpack.unpack_pbo(pbo_path, world, world_size, log=log)
    result = {"tiles": tiles, "classes": 0, "buildings_error": ""}
    addons = os.path.dirname(os.path.abspath(pbo_path))
    vanilla, mod = buildings_pbos(addons)
    if not vanilla and not mod:
        result["buildings_error"] = "рядом с PBO нет файлов игры — здания не собраны"
        return result
    try:
        result["classes"] = build_buildings.generate_from_pbos(
            vanilla + mod, world,
            str(paths.buildings_cache / f"{world}.json"),
            shared_path=str(paths.buildings_cache / SHARED),
            shared_pbos=vanilla if mod else None,
            log=log)
    except Exception as error:                   # подложка уже есть, зданиями не рискуем
        result["buildings_error"] = str(error)
    return result
