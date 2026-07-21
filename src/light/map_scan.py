"""Разведка папки с PBO: где лежат тайлы, а где — миссия CE.

У модов всё раскидано по архивам с произвольными именами: тайлы обычно в `data.pbo`,
миссия (`areaflags.map` + xml экономики) — в отдельном, у DeerIsle это `ce.pbo`. Искать
по именам бессмысленно, поэтому смотрим содержимое.

Читаются только заголовки архивов, поэтому папка на десяток гигабайт просматривается за
доли секунды (данные не трогаются вовсе). Один проход отвечает на оба вопроса сразу."""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from core import pbo

# Файлы миссии, которые интересны редактору. Имена — как в `light.project.ROLES`,
# ключи записей PBO приходят в нижнем регистре и через "/".
MISSION_FILES = (
    "areaflags.map",
    "cfglimitsdefinition.xml",
    "cfglimitsdefinitionuser.xml",
    "mapgroupproto.xml",
    "mapgrouppos.xml",
    "cfgeconomycore.xml",
    "db/types.xml",
    "db/events.xml",
    "cfgenvironment.xml",
    "cfgeventspawns.xml",
)


@dataclass
class Finding:
    """Что нашлось в одном PBO."""

    path: str
    tiles: int = 0                               # число спутниковых тайлов
    mission: list[str] = field(default_factory=list)   # имена найденных файлов миссии
    prefix: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def has_areaflags(self) -> bool:
        return "areaflags.map" in self.mission


def scan_pbo(path: str) -> Finding | None:
    """Разобрать один архив. None — заголовок не читается (битый или чужой формат)."""
    try:
        entries, prefix = pbo.read_header(path)
    except Exception:
        return None
    tiles = sum(1 for key in entries if key.startswith("layers/s_") and "_lco" in key)
    mission = [name for name in MISSION_FILES if name in entries]
    if not tiles and not mission:
        return None
    return Finding(path=path, tiles=tiles, mission=mission, prefix=prefix)


def scan_folder(folder: str, recursive: bool = True) -> list[Finding]:
    """Все находки папки. `recursive` — заглядывать и во вложенные Addons (корень воркшопа)."""
    seen: set[str] = set()
    paths: list[str] = sorted(glob.glob(os.path.join(folder, "*.pbo")))
    if recursive:
        for root, dirs, _files in os.walk(folder):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            if os.path.basename(root).lower() == "addons" and root != folder:
                paths += sorted(glob.glob(os.path.join(root, "*.pbo")))
    findings = []
    for path in paths:
        key = os.path.normcase(os.path.abspath(path))
        if key in seen:
            continue
        seen.add(key)
        finding = scan_pbo(path)
        if finding:
            findings.append(finding)
    return findings


def tile_findings(findings: list[Finding]) -> list[Finding]:
    return [f for f in findings if f.tiles]


def mission_findings(findings: list[Finding]) -> list[Finding]:
    """Архивы с файлами миссии — сначала те, где есть areaflags.map (он главный)."""
    with_mission = [f for f in findings if f.mission]
    return sorted(with_mission, key=lambda f: (not f.has_areaflags, -len(f.mission)))
