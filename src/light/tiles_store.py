"""Хранилище подложек (пирамид тайлов).

Ищем готовые пирамиды в двух местах (см. `core.paths.AppPaths.tile_roots`): сперва в
кэше распакованных пользователем подложек (`appdata/tiles`), затем в bundled-ассетах,
поставляемых с приложением (`assets/tiles`). Мир (метры) берём из areaflags — подложка
масштабируется под него. Формат пирамиды — `core.tiles` (meta.json + {z}/{x}_{y}.jpg)."""
from __future__ import annotations

from core.paths import paths
from core.tiles import TileMeta, find_tiles


def available_worlds() -> list[str]:
    """Имена миров, для которых есть готовая пирамида (meta.json), из всех корней."""
    found: list[str] = []
    for root in paths.tile_roots():
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            if (child / "meta.json").is_file() and child.name not in found:
                found.append(child.name)
    return found


def find(world: str) -> TileMeta | None:
    """TileMeta мира из любого корня (кэш приоритетнее bundled)."""
    for root in paths.tile_roots():
        meta = find_tiles(root, world)
        if meta:
            return meta
    return None
