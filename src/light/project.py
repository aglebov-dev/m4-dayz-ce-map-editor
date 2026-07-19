"""Модель проекта: какие файлы, от какого провайдера, + снапшот для сравнения.

Провайдер (ФС/SFTP) МАТЕРИАЛИЗУЕТ выбранные файлы в локальный кэш проекта в служебной
папке; ядро читает уже локальную копию. Снапшот — копия материализованных данных на
момент создания проекта, эталон для Дифа."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from core.paths import paths
from light.providers import DataProvider, make_provider


@dataclass
class FileRole:
    key: str
    title: str
    tool: str                # какой инструмент требует (для блокировки/подсказки)
    required: bool           # без него проект бессмысленен
    candidates: list[str]    # относительные пути-кандидаты внутри миссии


# Роли файлов. Пути — относительно папки миссии (mpmissions/<world>).
ROLES: list[FileRole] = [
    FileRole("areaflags", "areaflags.map", "map", True, ["areaflags.map"]),
    FileRole("cfglimits", "cfglimitsdefinition.xml", "map", True,
             ["cfglimitsdefinition.xml"]),
    FileRole("cfglimitsuser", "cfglimitsdefinitionuser.xml", "map", False,
             ["cfglimitsdefinitionuser.xml"]),
    FileRole("mapgroupproto", "mapgroupproto.xml", "objects", False,
             ["mapgroupproto.xml"]),
    FileRole("mapgrouppos", "mapgrouppos.xml", "objects", False,
             ["mapgrouppos.xml"]),
    FileRole("economycore", "cfgeconomycore.xml", "economy", False,
             ["cfgeconomycore.xml"]),
    FileRole("types", "db/types.xml", "economy", False, ["db/types.xml"]),
    FileRole("environment", "cfgenvironment.xml", "territories", False,
             ["cfgenvironment.xml"]),
]


@dataclass
class Project:
    id: str
    name: str
    provider_cfg: dict
    mission_name: str                       # напр. "mpmissions/dayzOffline.chernarusplus"
    files: dict = field(default_factory=dict)   # role -> rel-путь внутри миссии
    background: str = ""                    # "" | "tiles:<world>" | "image:<path>"

    # --- пути (все через core.paths.AppPaths) ---
    # Всё содержимое проекта живёт в ОДНОМ месте — appdata/projects/<id>:
    #   config.json, snapshot/, data/<миссия>/…  Внешних папок нет (единое место).
    @property
    def dir(self) -> Path:
        """Папка проекта в appdata: конфиг, снапшот и материализованные данные."""
        return paths.ensure(paths.project(self.id))

    @property
    def workdir(self) -> Path:
        """Корень, который читает ядро: `scan_workdir` ищет миссию в `<workdir>/data`."""
        return self.dir

    @property
    def data_dir(self) -> Path:
        """Куда материализуются файлы миссии — прямо в `<dir>/data` (без подпапки по имени
        миссии; имя миссии хранится в config.json)."""
        return self.workdir / "data"

    @property
    def snapshot_dir(self) -> Path:
        return self.dir / "snapshot"

    @property
    def mission_dir(self) -> Path:
        """Папка с файлами миссии = сама data/ (плоская раскладка; имя миссии — в config.json)."""
        return self.data_dir

    # --- сохранение конфигурации ---
    def save(self):
        cfg = {
            "id": self.id, 
            "name": self.name, 
            "provider": _safe_provider(self.provider_cfg),
            "mission_rel": self.mission_name, 
            "files": self.files,
            "background": self.background,
        }
        with open(self.dir / "config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)

    @staticmethod
    def load(project_id: str) -> "Project":
        p = paths.project(project_id) / "config.json"
        with open(p, encoding="utf-8") as f:
            c = json.load(f)
        return Project(c["id"], c["name"], c["provider"], c["mission_rel"],
                       c.get("files", {}), c.get("background", ""))

    def has_snapshot(self) -> bool:
        return os.path.isdir(self.snapshot_dir) and bool(os.listdir(self.snapshot_dir))


def _safe_provider(cfg: dict) -> dict:
    """Пароль SFTP в конфиг не пишем — только способ входа."""
    out = dict(cfg)
    out.pop("password", None)
    return out


def new_id(name: str) -> str:
    """Свободный id проекта из имени: только буквы/цифры, уникален среди appdata/projects."""
    base = "".join(c if c.isalnum() else "_" for c in name)[:32] or "proj"
    project_id, number = base, 2
    while paths.project(project_id).is_dir():
        project_id = f"{base}_{number}"
        number += 1
    return project_id


def list_projects() -> list[dict]:
    out = []
    root = paths.projects
    if not root.is_dir():
        return out
    for child in sorted(root.iterdir()):
        cfg = child / "config.json"
        if cfg.is_file():
            try:
                out.append(json.loads(cfg.read_text(encoding="utf-8")))
            except Exception:
                pass
    return out


# ---------- обнаружение миссий и файлов у провайдера ----------

def find_missions(provider: DataProvider) -> list[str]:
    """Папки миссий: mpmissions/* с areaflags.map или cfglimitsdefinition.xml;
    либо сам корень, если это папка миссии."""
    found: list[str] = []
    for base in ("mpmissions", ""):
        for name in provider.list_dir(base):
            rel = f"{base}/{name}".strip("/")
            if (provider.exists(f"{rel}/areaflags.map") or provider.exists(f"{rel}/cfglimitsdefinition.xml")):
                found.append(rel)
            # if (provider.exists(f"{rel}/data/mission/areaflags.map") or provider.exists(f"{rel}/data/mission/cfglimitsdefinition.xml")):
            #     found.append(f"{rel}/data/mission")
    if not found and provider.exists("areaflags.map"):
        found.append("")
    return found


def world_name(mission_rel: str) -> str:
    """Короткое имя мира для PBO: 'dayzOffline.chernarusplus' -> 'chernarusplus'."""
    base = os.path.basename(mission_rel.rstrip("/"))
    return base.split(".")[-1] if "." in base else base


def read_world_size(provider: DataProvider, mission_rel: str) -> int:
    """Размер мира (метры) из заголовка areaflags.map (uint32 по смещению 8). 0 — нет."""
    import struct
    rel = f"{mission_rel}/areaflags.map".strip("/")
    try:
        hdr = provider.read_header(rel, 24)
        if len(hdr) < 24:
            return 0
        return int(struct.unpack("<6I", hdr)[2])
    except Exception:
        return 0


def resolve_files(provider: DataProvider, mission_rel: str) -> dict:
    """role -> rel-путь для файлов, которые реально есть у провайдера."""
    files = {}
    for role in ROLES:
        for cand in role.candidates:
            rel = f"{mission_rel}/{cand}".strip("/")
            if provider.exists(rel):
                files[role.key] = cand
                break
    return files


def missing_required(files: dict) -> list[str]:
    return [r.title for r in ROLES if r.required and r.key not in files]


# ---------- материализация и снапшот ----------

def materialize(project: Project, provider: DataProvider) -> str:
    """Скачать/скопировать выбранные файлы миссии прямо в data/. Возвращает её путь."""
    target = str(project.data_dir)
    if os.path.isdir(target):
        shutil.rmtree(target)
    for role_key, cand in project.files.items():
        rel = f"{project.mission_name}/{cand}".strip("/")
        local = os.path.join(target, cand.replace("/", os.sep))
        provider.fetch_to(rel, local)
    return target


def make_snapshot(project: Project):
    """Снимок материализованной миссии — эталон Дифа (перезаписывает старый). Кладём файлы
    прямо в snapshot/ (без подпапки по имени миссии)."""
    if os.path.isdir(project.snapshot_dir):
        shutil.rmtree(project.snapshot_dir)
    shutil.copytree(str(project.data_dir), str(project.snapshot_dir))


def delete_snapshot(project: Project):
    if os.path.isdir(project.snapshot_dir):
        shutil.rmtree(project.snapshot_dir)


def load_snapshot_from(project: Project, provider: DataProvider, mission_rel: str):
    """Ручной снапшот: взять areaflags+cfglimits у другого источника (сервер/проект BI).
    Кладём прямо в snapshot/."""
    if os.path.isdir(project.snapshot_dir):
        shutil.rmtree(project.snapshot_dir)
    for cand in ("areaflags.map", "cfglimitsdefinition.xml",
                 "cfglimitsdefinitionuser.xml"):
        rel = f"{mission_rel}/{cand}".strip("/")
        if provider.exists(rel):
            provider.fetch_to(rel, os.path.join(str(project.snapshot_dir), cand))


def snapshot_mission_dir(project: Project) -> str | None:
    """Папка снапшота для чтения ядром — сама snapshot/ (плоская раскладка)."""
    return str(project.snapshot_dir) if project.has_snapshot() else None
