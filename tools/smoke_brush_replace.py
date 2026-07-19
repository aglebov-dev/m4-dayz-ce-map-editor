"""Смоук режима кисти «Замена»: мазок ставит активный слой и снимает прочие ВКЛЮЧЁННЫЕ
слои, выключенные не трогает, undo откатывает всё ОДНИМ шагом, ластик и замена
взаимоисключающи. Offscreen, сервер/проект не нужны — areaflags синтетический.

Запуск из корня репозитория:  .venv/Scripts/python.exe tools/smoke_brush_replace.py"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import numpy as np
from PySide6.QtWidgets import QApplication

app = QApplication([])
from core.areaflags import AreaFlags
from light.main_window import LightMainWindow

GX = GY = 40                                     # 40x40 ячеек по 10 м = 400 м карта
areaflags = AreaFlags(
    grid_x=GX, grid_y=GY, size_x=400, size_y=400,
    usages=["Military", "Town", "Farm"], values=["Tier1", "Tier2"],
    usage=np.zeros(GX * GY, dtype=np.uint32), tier=np.zeros(GX * GY, dtype=np.uint8))

# всё поле заранее размечено ВСЕМИ флагами — чтобы увидеть, что именно снимется
areaflags.usage[:] = 0b111                       # Military|Town|Farm
areaflags.tier[:] = 0b11                         # Tier1|Tier2

w = LightMainWindow()
w.areaflags = areaflags
# снимок «как на диске» — обычно ставится при загрузке проекта, тут ставим сами
w._af_orig = (areaflags.usage.copy(), areaflags.tier.copy())
w.layers.populate(areaflags, tiers_on=False)
w.brush_panel.populate(
    [(f"tier:{n}", n, (1, 2, 3)) for n in areaflags.values],
    [(f"usage:{n}", n, (4, 5, 6)) for n in areaflags.usages])
app.processEvents()

# включаем Military (рисуемый), Town и Tier1; Farm и Tier2 ОСТАВЛЯЕМ выключенными
for key in ("usage:Military", "usage:Town", "tier:Tier1"):
    row = next(r for r in w.layers.panel._rows if r.key == key)
    row.btn.setChecked(True)
app.processEvents()
visible = set(w.layers.visible_keys())
print("включены:", sorted(visible))
assert {"usage:Military", "usage:Town", "tier:Tier1"} <= visible

w.brush_panel.select_layer("usage:Military")
w.brush_panel.sw_replace.setChecked(True)        # режим «Замена»
app.processEvents()
assert w._replace is True and w._erase is False, (w._replace, w._erase)
targets = set(w._replace_targets("usage:Military"))
print("замещаются:", sorted(targets))
assert "usage:Military" not in targets, "рисуемый слой сам себя не стирает"
assert "usage:Farm" not in targets and "tier:Tier2" not in targets, \
    "выключенные слои трогать нельзя"

def bits_at(x, z):
    col, row = int(x // areaflags.cell_size), int(z // areaflags.cell_size)
    i = row * GX + col
    return int(areaflags.usage[i]), int(areaflags.tier[i])

before = bits_at(200.0, 200.0)
w.on_stroke_started()
w.brush_panel.sld.setValue(30)                   # радиус 30 м
w.on_paint(200.0, 200.0)
w.on_stroke_finished()
after_u, after_t = bits_at(200.0, 200.0)
print(f"в центре мазка: usage {before[0]:03b}->{after_u:03b}  tier {before[1]:02b}->{after_t:02b}")

MIL, TOWN, FARM = 1 << 0, 1 << 1, 1 << 2
T1, T2 = 1 << 0, 1 << 1
assert after_u & MIL, "активный слой Military должен быть поставлен"
assert not after_u & TOWN, "включённый Town должен быть снят"
assert after_u & FARM, "выключенный Farm трогать нельзя"
assert not after_t & T1, "включённый Tier1 должен быть снят"
assert after_t & T2, "выключенный Tier2 трогать нельзя"

# вне мазка всё осталось как было
far_u, far_t = bits_at(20.0, 20.0)
assert (far_u, far_t) == (0b111, 0b11), (far_u, far_t)
print("вне мазка не изменилось")

# undo откатывает ВСЮ замену одним шагом
assert w.history.depth[0] == 1, f"замена должна быть ОДНИМ шагом истории: {w.history.depth}"
w.on_undo()
assert bits_at(200.0, 200.0) == before, bits_at(200.0, 200.0)
print("undo одним шагом вернул исходное состояние")

# ластик и замена взаимоисключающи
w.brush_panel.sw_erase.setChecked(True)
app.processEvents()
assert w._erase is True and w._replace is False, (w._erase, w._replace)
assert not w.brush_panel.sw_replace.isChecked()
print("ластик выключил «Замену» (и наоборот)")

print("OK")
