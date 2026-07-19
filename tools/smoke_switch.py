"""Смоук: смена карты (мир 15360→12800) — world_size и масштаб следуют за текущей
картой, а не за фиксированным миром проекта. Пропуск, если нет ванильного Enoch."""
import os
import shutil
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="m4_switch_")
os.environ["M4_HOME"] = HOME

import numpy as np
from PySide6.QtWidgets import QApplication

from light import project as P
from light.main_window import LightMainWindow

SERVER_ROOT = os.environ.get("M4_SMOKE_SERVER_ROOT")
if not SERVER_ROOT:
    sys.exit("Задай M4_SMOKE_SERVER_ROOT — корень сервера DayZ (содержит mpmissions/)")
CH = os.path.join(SERVER_ROOT, "mpmissions", "dayzOffline.chernarusplus")
EN = r"D:\steam\steamapps\common\DayZServer\mpmissions\dayzOffline.enoch"

if not os.path.isdir(EN):
    print("нет ванильного Enoch — пропуск"); print("OK"); sys.exit(0)

WD = os.path.join(HOME, "wd")
for src, name in [(CH, "dayzOffline.chernarusplus"), (EN, "dayzOffline.enoch")]:
    d = os.path.join(WD, "mpmissions", name)
    os.makedirs(d)
    for f in ("areaflags.map", "cfglimitsdefinition.xml", "cfglimitsdefinitionuser.xml"):
        p = os.path.join(src, f)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(d, f))

app = QApplication(sys.argv)
proj = P.Project("sw", "SW", {"kind": "local", "root": WD},
                 "mpmissions/dayzOffline.chernarusplus",
                 {"areaflags": "areaflags.map", "cfglimits": "cfglimitsdefinition.xml"})
proj.save()
w = LightMainWindow()
w.project = proj
w.load_workdir(WD)                               # оба мира в комбобоксе
app.processEvents()


def pick(world):
    for i in range(w.cmb_mission.count()):
        if w.cmb_mission.itemData(i).world == world:
            w.cmb_mission.setCurrentIndex(i)
            return
    raise AssertionError(f"нет мира {world}")


pick("chernarusplus")
app.processEvents()
assert w.view._world_size == w.areaflags.size_x == 15360
# оверлей строится под текущий мир
ov = w.view._overlays.get("tier:Tier1")
print("chernarus: world_size 15360 ок")

pick("enoch")
app.processEvents()
assert w.view._world_size == w.areaflags.size_x == 12800, \
    f"после смены на Enoch world_size={w.view._world_size}, а карта {w.areaflags.size_x}"
assert w.areaflags.grid_x == 4096
mil = w.areaflags.usages.index("Military")
assert int(np.count_nonzero(w.areaflags.usage & np.uint32(1 << mil))) > 0
# маркер/оверлеи используют текущий world_size — проверим set_marker в пределах мира
w.view.set_marker(12000.0, 12000.0)
assert w.view._marker is not None
print("enoch: world_size 12800, разметка и масштаб следуют за картой")

# назад на chernarus — снова 15360 (не залипло)
pick("chernarusplus")
app.processEvents()
assert w.view._world_size == 15360
print("возврат на chernarus: world_size 15360 (не залипло)")

# --- ПЕРЕОТКРЫТИЕ через диалог: эноч → черно не грузит эноч ---
from light.config_dialog import ProjectConfigDialog


def open_via_dialog(existing, world):
    dlg = ProjectConfigDialog(w, existing=existing)
    dlg.ed_folder.setText(WD)
    dlg._connect()
    for i in range(dlg.cmb_mission.count()):
        if world in (dlg.cmb_mission.itemData(i) or ""):
            dlg.cmb_mission.setCurrentIndex(i)
            break
    dlg._accept()
    return dlg.result_project


projE = open_via_dialog(None, "enoch")
w.open_project(projE); app.processEvents()
assert w.view._world_size == 12800
projC = open_via_dialog(w.project, "chernarusplus")   # existing=enoch, открываем черно
assert projC.id != projE.id, "другая миссия должна дать НОВЫЙ проект (свой id/папку)"
assert os.listdir(projC.data_dir) == ["dayzOffline.chernarusplus"], \
    os.listdir(projC.data_dir)
w.open_project(projC); app.processEvents()
assert w.view._world_size == 15360, "после 'открыть черно' должен грузиться черно"
print("переоткрытие эноч→черно: новый проект, чистая папка, грузится черно")

shutil.rmtree(HOME, ignore_errors=True)
print("OK")
