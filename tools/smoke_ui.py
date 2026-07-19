"""Смоук L1/L3/L4/L5: конфиг-диалог, блокировка инструментов, Диф со снапшотом,
экспорт. Offscreen; провайдер — локальное зеркало."""
import os
import shutil
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="m4_light_ui_")
os.environ["M4_HOME"] = HOME

import numpy as np
from PySide6.QtWidgets import QApplication

from light import project as P
from light.gating import tool_ok, tool_status
from light.main_window import LightMainWindow
from light.providers import LocalProvider

SERVER_ROOT = os.environ.get("M4_SMOKE_SERVER_ROOT")
if not SERVER_ROOT:
    sys.exit("Задай M4_SMOKE_SERVER_ROOT — корень сервера DayZ (содержит mpmissions/)")

app = QApplication(sys.argv)

# --- gating (чистая логика) ---
full = {"areaflags": "a", "cfglimits": "b", "mapgroupproto": "c", "mapgrouppos": "d",
        "economycore": "e", "types": "f", "environment": "g"}
st = tool_status(full)
assert all(s["ok"] for s in st.values())
part = {"areaflags": "a", "cfglimits": "b"}          # только карта
assert tool_ok(part, "map") and not tool_ok(part, "objects")
assert "mapgroupproto.xml" in tool_status(part)["objects"]["missing"]
print("gating: полный набор — всё ок; только карта — Объекты/Спавн заблокированы")

# --- собрать проект напрямую (как сделал бы диалог) ---
prov = LocalProvider(SERVER_ROOT)
mrel = next(m for m in P.find_missions(prov) if "chernarusplus" in m)
files = P.resolve_files(prov, mrel)
proj = P.Project("uitest", "Chernarus", {"kind": "local", "root": SERVER_ROOT},
                 mrel, files)
proj.save()
P.materialize(proj, prov)
P.make_snapshot(proj)

# --- старт БЕЗ проекта: все инструменты закрыты и заблокированы ---
w = LightMainWindow()
w.resize(1200, 800)
w.show()
app.processEvents()
assert w.project is None
for name in w._docks:
    assert not w._docks[name].isVisible(), f"{name} должен быть закрыт без проекта"
    assert not w._docks[name].toggleViewAction().isEnabled(), f"{name} кнопка заблокирована"
assert not w.btn_bi_export.isEnabled()
assert not w.btn_save.isEnabled() and not w.btn_reload.isEnabled()
assert "dock_territories" not in w._docks, "территории удалены из лёгкого редактора"
print("старт без файлов: все инструменты закрыты, кнопки заблокированы")

# --- открыть проект: инструменты доступны ---
w.open_project(proj)
app.processEvents()
assert w.project is proj and w.areaflags is not None
assert w.btn_bi_export.isEnabled()
# панели прилипают только к бокам (не к верху/низу)
from PySide6.QtCore import Qt as _Qt
allowed = w._docks["dock_layers"].allowedAreas()
assert not (allowed & _Qt.DockWidgetArea.TopDockWidgetArea)
assert not (allowed & _Qt.DockWidgetArea.BottomDockWidgetArea)
for name, tool in [("dock_layers", "map"), ("dock_objects", "objects"),
                   ("dock_items", "economy")]:
    assert w._docks[name].toggleViewAction().isEnabled(), name
assert w.btn_background.isHidden(), "кнопка Background убрана (подложка — при загрузке)"
assert w.btn_workdir.isHidden() and w.cmb_mission.isHidden(), \
    "Folder/Map убраны — миссия задаётся проектом"
assert w.brush_panel.minimumHeight() >= 200, "панель кисти не должна схлопываться"
print("проект открыт: карта загружена, инструменты доступны, доки только по бокам")

# --- блокировка: проект без объектов/экономики ---
files2 = {k: v for k, v in files.items() if k in ("areaflags", "cfglimits")}
proj2 = P.Project("uitest2", "MapOnly", {"kind": "local", "root": SERVER_ROOT},
                  mrel, files2)
proj2.save()
# материализуем только карту+флаги
P.materialize(proj2, prov)
P.make_snapshot(proj2)
w.open_project(proj2)
app.processEvents()
assert w._docks["dock_layers"].toggleViewAction().isEnabled()   # карта — есть
assert not w._docks["dock_objects"].toggleViewAction().isEnabled()  # объектов нет
assert not w._docks["dock_items"].toggleViewAction().isEnabled()    # экономики нет
assert "mapgroupproto" in w._docks["dock_objects"].toggleViewAction().toolTip()
assert not w._docks["dock_objects"].isVisible()      # заблокированный док спрятан
print("блокировка: без объектов/экономики их доки выключены с подсказкой")

# --- выделение области НЕ открывает Спавн; статистика поднимается ---
w.open_project(proj)                                  # полный проект снова
app.processEvents()
w.dock_loot.hide(); app.processEvents()
X0, Z0, X1, Z1 = 6000.0, 6000.0, 8000.0, 8000.0
w.view.set_region(X0, Z0, X1, Z1)
w.on_region_selected(X0, Z0, X1, Z1)
app.processEvents()
assert not w.dock_loot.isVisible(), "выделение не должно открывать Спавн"
assert w.loot_panel._counts is not None               # сводка посчитана (но не поднята)
assert w.view.region() is not None
print("выделение: Спавн не открылся, сводка посчитана")

# снятие выделения -> прямоугольник пропал, статистика -> вся карта
from ui.stats_panel import SCOPE_MAP
w.on_clear_region()
app.processEvents()
assert w.view.region() is None                        # выделение пропало
assert w.stats_panel.cmb_scope.currentIndex() == SCOPE_MAP  # статистика -> вся карта
print("снятие выделения: прямоугольник убран, статистика на всю карту")

# --- экспорт в BI: areaflags + cfglimits + TGA-слои + проект XML + map.png ---
from core.bi_export import export_project
dest = tempfile.mkdtemp(prefix="m4_bi_export_")
colors = {f"tier:{n}": (1, 2, 3) for n in w.areaflags.values}
# подложка одним файлом: подсунем фейковый map.png как источник
bg = os.path.join(HOME, "map.png")
from PIL import Image
Image.new("RGB", (64, 64), (10, 20, 30)).save(bg)
info = export_project(w.areaflags, dest,
                      cfglimits_src=os.path.join(proj.mission_dir, "cfglimitsdefinition.xml"),
                      colors=colors, world="chernarusplus", background_png=bg)
assert os.path.isfile(os.path.join(dest, "areaflags.map"))
assert os.path.isfile(os.path.join(dest, "cfglimitsdefinition.xml"))
assert os.path.isfile(os.path.join(dest, "chernarusplus.xml"))
assert info["background"] and os.path.isfile(os.path.join(dest, "map.png"))
n_tga = len([f for f in os.listdir(os.path.join(dest, "layers")) if f.endswith(".tga")])
assert n_tga == info["layers"] == len(w.areaflags.values) + len(w.areaflags.usages)
# TGA читается нашим же ридером и совпадает с планом флага
from core.ce_project import read_tga_gray
mil_tga = read_tga_gray(os.path.join(dest, "layers", "usgFlg_Military.tga"))[::-1] != 0
assert np.array_equal(mil_tga, w.areaflags.plane("Military"))
print(f"экспорт в BI: areaflags+cfglimits+{n_tga} TGA+проект; TGA=план флага")
shutil.rmtree(dest, ignore_errors=True)

# --- ориентация Дифа: мои правки = «Появилось» (относительно загруженной) ---
w.open_project(proj)
app.processEvents()
snap = P.snapshot_mission_dir(proj)              # эталон «до» (исходные данные)
af = w.areaflags
from core.brush import stamp as _stamp
from core.writer import save_areaflags as _save
_stamp(af, "usage:Military", 3000.0, 3000.0, 120.0)   # ДОБАВИЛ разметку в текущую
_save(af, backup=False)
w.load_diff(os.path.join(snap, "areaflags.map"))
app.processEvents()
# в таблице у Military «Появилось» > 0 (это моя правка), «Пропало» = 0
tbl = w.diff_panel.tbl
r_mil = next(r for r in range(tbl.rowCount())
             if tbl.item(r, 0).data(256) == "usage:Military")
added = tbl.item(r_mil, 1).value      # колонка «Появилось»
removed = tbl.item(r_mil, 2).value    # колонка «Пропало»
assert added > 0 and removed == 0, (added, removed)
print(f"ориентация дифа: моя правка Military в «Появилось» ({added:.0f}), «Пропало» 0")

shutil.rmtree(HOME, ignore_errors=True)
print("OK")
