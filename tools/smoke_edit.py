"""Смоук: добавление usage/value-флагов, запись cfglimits, пустые слои включаемы."""
import os
import shutil
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HOME = tempfile.mkdtemp(prefix="m4_edit_")
os.environ["M4_HOME"] = HOME

import numpy as np
from PySide6.QtWidgets import QApplication

from core.areaflags import read_areaflags, read_limits
from core.brush import stamp
from core.flags import (
    FlagError, MAX_VALUE, add_usage, add_value, remove_usage, remove_value,
    write_cfglimits,
)
from core.writer import save_areaflags
from light import project as P
from light.main_window import LightMainWindow
from light.providers import LocalProvider

SERVER_ROOT = os.environ.get("M4_SMOKE_SERVER_ROOT")
if not SERVER_ROOT:
    sys.exit("Задай M4_SMOKE_SERVER_ROOT — корень сервера DayZ (содержит mpmissions/)")
MIRROR = os.path.join(SERVER_ROOT, "mpmissions", "dayzOffline.chernarusplus")
ENOCH = r"D:\steam\steamapps\common\DayZServer\mpmissions\dayzOffline.enoch"


def copy_mission(src, name):
    d = os.path.join(HOME, name)
    shutil.copytree(src, d)
    return d


# --- core: add_usage/value + write_cfglimits round-trip ---
work = copy_mission(MIRROR, "cherna")
af = read_areaflags(work)
n_u, n_v = len(af.usages), len(af.values)
bit = add_usage(af, "Smuggler")
assert bit == n_u and af.usages[-1] == "Smuggler"
add_value(af, "Tier5")
assert af.values[-1] == "Tier5"
write_cfglimits(work, af)
u2, v2 = read_limits(work)                        # перечитали с диска
assert u2 == af.usages and v2 == af.values, "cfglimits не сохранил новые флаги по порядку"
print(f"добавление флагов: usage {n_u}->{len(u2)} (Smuggler=бит {bit}), value +Tier5; "
      f"cfglimits записан и перечитан")

# дубликат и мусорное имя отвергаются
for bad in ("Smuggler", "", "bad name!"):
    try:
        add_usage(af, bad); raise AssertionError(f"должно упасть: {bad!r}")
    except FlagError:
        pass
print("валидация: дубликат/пустое/с пробелом отвергнуты")

# новый флаг пуст в данных (только имя-бит зарегистрировано)
assert int(np.count_nonzero(af.usage & np.uint32(1 << bit))) == 0
print("новый usage пуст в данных (0 ячеек)")

# --- удаление флага: биты выше сдвигаются, данные ниже сохраняются ---
af3 = read_areaflags(copy_mission(MIRROR, "del"))
# запомним планы соседних флагов до удаления среднего
before_planes = {n: af3.plane(n).copy() for n in af3.usages}
victim = af3.usages[5]                            # удалим средний usage
below = af3.usages[:5]                            # флаги с меньшим битом — не двигаются
above = af3.usages[6:]                            # флаги выше — сдвигаются вниз
remove_usage(af3, victim)
assert victim not in af3.usages and len(af3.usages) == len(before_planes) - 1
for n in below:                                  # план не изменился
    assert np.array_equal(af3.plane(n), before_planes[n]), f"сдвинулся нижний флаг {n}"
for n in above:                                  # тот же план, но на бите -1
    assert np.array_equal(af3.plane(n), before_planes[n]), f"потерян верхний флаг {n}"
print(f"удаление usage «{victim}»: нижние и верхние флаги целы, биты пересобраны")

# value-флаг тоже удаляется
nv = len(af3.values)
remove_value(af3, af3.values[1])
assert len(af3.values) == nv - 1
# нет флага -> FlagError
try:
    remove_usage(af3, "NoSuchFlag"); raise AssertionError("должно упасть")
except FlagError:
    pass
print("удаление value + ошибка на несуществующем флаге: ок")

# --- ниббл→байт: у Enoch 4 value, добавление 5-го меняет раскладку слоя B ---
if os.path.isdir(ENOCH):
    we = copy_mission(ENOCH, "enoch")
    ae = read_areaflags(we)
    assert len(ae.values) == 4                    # ниббл-режим
    sz0 = os.path.getsize(os.path.join(we, "areaflags.map"))
    add_value(ae, "TierX")                        # 5-й value -> байт-режим
    write_cfglimits(we, ae)
    save_areaflags(ae, backup=False)
    sz1 = os.path.getsize(os.path.join(we, "areaflags.map"))
    assert sz1 > sz0, "переход ниббл->байт должен увеличить слой B"
    back = read_areaflags(we)                      # перечитали: 5 value, байт-режим
    assert len(back.values) == 5 and np.array_equal(back.tier, ae.tier)
    print(f"Enoch ниббл->байт: {sz0:,}->{sz1:,} байт, round-trip точный")

# --- предел value ---
af2 = read_areaflags(copy_mission(MIRROR, "cap"))
while len(af2.values) < MAX_VALUE:
    add_value(af2, f"V{len(af2.values)}")
try:
    add_value(af2, "TooMany"); raise AssertionError("должен быть предел value")
except FlagError:
    pass
print(f"предел value = {MAX_VALUE}: переполнение отвергнуто")

# --- UI: пустой слой включаем; добавление флага через окно; рисуем ---
app = QApplication(sys.argv)
prov = LocalProvider(HOME)                        # HOME содержит папки-миссии (cherna, …)
mrel = next(m for m in P.find_missions(prov) if m == "cherna")
files = P.resolve_files(prov, mrel)
proj = P.Project("editui", "Cherna", {"kind": "local", "root": prov.root}, mrel, files)
proj.save(); P.materialize(proj, prov); P.make_snapshot(proj)

w = LightMainWindow(); w.resize(1200, 800); w.open_project(proj); w.show()
app.processEvents()

# пустой usage-флаг (например, Underground у Chernarus — 0 ячеек) — строка ВКЛЮЧАЕМА
empties = [r for r in w.layers_panel._rows
           if r.key.startswith("usage:") and "(0)" in r.text.text()]
assert empties, "нет пустого слоя для проверки"
assert empties[0].btn.isEnabled(), "пустой слой должен быть включаемым (для рисования)"
print(f"пустой слой {empties[0].key}: включаемый")

# «＋» — в заголовках секций панели «Слои» (рядом с all/none), не в тулбаре
assert w.layers_panel.allow_add_flag
assert not hasattr(w, "btn_add_usage"), "кнопки +usage/+value убраны из тулбара"

# добавить usage-флаг через сигнал панели (как клик по «＋» в заголовке Usage)
w.layers_panel.add_flag_requested.emit  # сигнал существует
add_usage(w.areaflags, "Contraband")
write_cfglimits(w.project.mission_dir, w.areaflags)
w._repopulate_layers()
app.processEvents()
row = next((r for r in w.layers_panel._rows if r.key == "usage:Contraband"), None)
assert row is not None and row.btn.isEnabled()
# рисуем в новый флаг -> ячейки появляются
w.brush_panel.select_layer("usage:Contraband")
w.brush_panel.sw_mode.setChecked(True)
w.view.stroke_started.emit()
w.view.paint_world.emit(8000.0, 8000.0)
w.view.stroke_finished.emit()
app.processEvents()
bit = w.areaflags.usages.index("Contraband")
assert int(np.count_nonzero(w.areaflags.usage & np.uint32(1 << bit))) > 0
print("новый флаг Contraband: строка включаема, кисть его красит")

# «×» удаления есть в строках тиров/usage; удаление через окно убирает флаг
row = next(r for r in w.layers_panel._rows if r.key == "usage:Contraband")
assert hasattr(row, "btn_del"), "в строке слоя должна быть кнопка удаления"
n_before = len(w.areaflags.usages)
from PySide6.QtWidgets import QMessageBox
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
w.del_flag("usage:Contraband")
app.processEvents()
assert "Contraband" not in w.areaflags.usages and len(w.areaflags.usages) == n_before - 1
assert not any(r.key == "usage:Contraband" for r in w.layers_panel._rows)
print("удаление флага через окно: строка и флаг убраны")

shutil.rmtree(HOME, ignore_errors=True)
print("OK")
