"""Смоук: хранилище подложек, поле background в проекте, загрузка тайлов по проекту,
контракт распаковщика."""
import os
import shutil
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="m4_bg_")
os.environ["M4_HOME"] = HOME

# внешний корень тайлов (каждый содержит tiles/<world>); задаётся env для смоука
TILES_ASSETS = os.environ.get("M4_SMOKE_TILES_ASSETS", "")
if TILES_ASSETS:
    os.environ["M4_TILES_DIRS"] = TILES_ASSETS

import numpy as np
from PySide6.QtWidgets import QApplication

from light import project as P
from light import tiles_store, tiles_unpack
from light.main_window import LightMainWindow
from light.providers import LocalProvider

MIRROR_ROOT = os.environ.get("M4_SMOKE_SERVER_ROOT")
if not MIRROR_ROOT:
    sys.exit("Задай M4_SMOKE_SERVER_ROOT — корень сервера DayZ (содержит mpmissions/)")

# --- хранилище: мир из внешнего корня виден, TileMeta находится ---
worlds = tiles_store.available_worlds()
assert "chernarusplus" in worlds, worlds
meta = tiles_store.find("chernarusplus")
assert meta is not None and meta.world_size == 15360
print(f"хранилище подложек: миры {worlds}; chernarusplus worldSize {meta.world_size} м "
      f"= {meta.world_size/1000:.2f} км")

# --- распаковщик: нативный (Python), путь PBO, понятные ошибки ---
assert tiles_unpack.available()                  # numpy+Pillow всегда
pbo = tiles_unpack.pbo_path(r"D:\game", "chernarusplus")
assert pbo.endswith(r"Addons\worlds_chernarusplus_data.pbo"), pbo
print(f"распаковщик: нативный Python, PBO {os.path.basename(pbo)}")

# нет папки игры -> понятная ошибка; нет PBO в существующей папке -> тоже
try:
    tiles_unpack.unpack(os.path.join(HOME, "nope"), "chernarusplus", 15360)
    raise AssertionError("нет папки игры — должно падать")
except tiles_unpack.UnpackError as e:
    assert "нет папки игры" in str(e)
try:
    tiles_unpack.unpack(HOME, "chernarusplus", 15360)   # HOME без Addons/*.pbo
    raise AssertionError("нет PBO — должно падать")
except tiles_unpack.UnpackError as e:
    assert "PBO" in str(e)
print("распаковщик: понятные ошибки (нет папки игры / нет PBO мира)")

# размер мира из заголовка areaflags — без чтения файла целиком
size = P.read_world_size(prov_hdr := LocalProvider(MIRROR_ROOT),
                         next(m for m in P.find_missions(LocalProvider(MIRROR_ROOT))
                              if "cherna" in m))
assert size == 15360, size
assert P.world_name("mpmissions/dayzOffline.chernarusplus") == "chernarusplus"
print(f"размер мира из заголовка: {size} м; имя мира для PBO: chernarusplus")

# --- проект: background сохраняется/читается ---
prov = LocalProvider(MIRROR_ROOT)
mrel = next(m for m in P.find_missions(prov) if "cherna" in m)
files = P.resolve_files(prov, mrel)
proj = P.Project("bg", "Cherna", {"kind": "local", "root": MIRROR_ROOT}, mrel, files,
                 background="tiles:chernarusplus")
proj.save()
P.materialize(proj, prov)
P.make_snapshot(proj)
assert P.Project.load("bg").background == "tiles:chernarusplus"
print("проект: background=tiles:chernarusplus сохранён и загружен")

# --- окно: подложка-тайлы применяется при открытии проекта ---
app = QApplication(sys.argv)
w = LightMainWindow()
w.resize(1200, 800)
w.open_project(proj)
w.show()
app.processEvents()
# сцена карты не пуста (тайлы задника загружены) и мир 15360
assert w.view._meta is not None and w.view._world_size == 15360
assert len(w.view.scene().items()) > 0
assert "тайлы" in w.lbl_bg.text()
print("окно: подложка-тайлы загружена, мир 15360 м, масштабирование под размер карты")

# --- миссия В КОРНЕ: мир из имени папки (не chernarusplus), но подложка выбрана явно ---
# грузим по выбору project.background, сверяя размер мира
# (чинит "не грузится подложка для (корень)")
mission_root = os.path.join(MIRROR_ROOT, "mpmissions", "dayzOffline.chernarusplus")
prov_root = LocalProvider(mission_root)          # корень = сама папка миссии -> mrel ""
proj_root = P.Project("bgroot", "Root", {"kind": "local", "root": mission_root}, "",
                      P.resolve_files(prov_root, ""), background="tiles:chernarusplus")
proj_root.save()
P.materialize(proj_root, prov_root)
P.make_snapshot(proj_root)
w.open_project(proj_root)
app.processEvents()
mw = w.current_mission().world
assert mw != "chernarusplus"                     # мир миссии-в-корне не совпадает с тайлами
assert w.view._meta is not None and w.view._world_size == 15360, \
    "подложка по явному выбору должна грузиться и для миссии-в-корне"
print(f"миссия в корне (мир '{mw}'): подложка chernarusplus грузится по выбору")

# без подложки (background="") — окно грузится, сцена — пустой мир
proj2 = P.Project("bg2", "C2", {"kind": "local", "root": MIRROR_ROOT}, mrel, files,
                  background="")
proj2.save(); P.materialize(proj2, prov); P.make_snapshot(proj2)
w.open_project(proj2)
app.processEvents()
assert w.view._world_size == 15360               # мир известен из areaflags
print("без подложки: мир из areaflags, карта работает")

shutil.rmtree(HOME, ignore_errors=True)
print("OK")
