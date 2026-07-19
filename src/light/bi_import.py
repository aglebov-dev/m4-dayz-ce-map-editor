"""Создание проекта приложения из проекта CE Tool (BI) — обвязка над `core.ce_import`.

`core.ce_import` даёт (AreaFlags, cfglimits-XML); здесь это материализуется в обычный проект
appdata: пишем сгенерированную миссию в `<project>/data/mission/`, сохраняем конфиг и снапшот.
Провайдер данных не нужен (файлы синтезируются из TGA-слоёв), поэтому `provider_cfg` хранит
kind='bi' и путь к папке CE Tool — этого хватает, чтобы `reload` переимпортировал заново."""
from __future__ import annotations

import os
import shutil

from core.ce_import import import_ce_project, write_mission
from core.ce_project import read_project
from light import project as P

# Единственная миссия BI-проекта (данные CE Tool — одна карта).
_MISSION = "mission"
# Файлы, которые синтезирует импорт (роли для гейтинга инструментов: работает «Карта»).
_FILES = {"areaflags": "areaflags.map", "cfglimits": "cfglimitsdefinition.xml"}


def read_summary(folder: str):
    """Прочитать проект CE Tool для предпросмотра (сетка/мир/слои). ValueError — не проект."""
    return read_project(folder)


def create_project(folder: str, name: str) -> P.Project:
    """Импортировать проект CE Tool из папки в новый проект приложения."""
    areaflags, cfglimits = import_ce_project(folder)
    project = P.Project(
        id=P.new_id(name),
        name=name,
        provider_cfg={"kind": "bi", "root": os.path.abspath(folder)},
        mission_name=_MISSION,
        files=dict(_FILES),
        background="")
    project.save()
    write_mission(areaflags, cfglimits, str(project.mission_dir))
    P.make_snapshot(project)
    return project


def rematerialize(project: P.Project) -> None:
    """Переимпорт из исходной папки CE Tool (для reload). Перезаписывает миссию."""
    folder = project.provider_cfg.get("root", "")
    areaflags, cfglimits = import_ce_project(folder)
    if os.path.isdir(project.mission_dir):
        shutil.rmtree(project.mission_dir)
    write_mission(areaflags, cfglimits, str(project.mission_dir))
