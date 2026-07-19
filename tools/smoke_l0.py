"""Смоук L0/L2: провайдеры, модель проекта, материализация, снапшот.
Локальный провайдер на боевом зеркале; SFTP — только проверка контракта (без сети)."""
import os
import shutil
import sys
import tempfile

SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC)

HOME = tempfile.mkdtemp(prefix="m4_light_home_")
os.environ["M4_HOME"] = HOME             # изолируем служебную папку

from light import project as P
from light.providers import (
    LocalProvider, ProviderError, make_provider, sftp_available,
)
from core.areaflags import read_areaflags
from core.diff import diff_maps

SERVER_ROOT = os.environ.get("M4_SMOKE_SERVER_ROOT")
if not SERVER_ROOT:
    sys.exit("Задай M4_SMOKE_SERVER_ROOT — корень сервера DayZ (содержит mpmissions/)")

# --- локальный провайдер: обнаружение миссий и файлов ---
prov = LocalProvider(SERVER_ROOT)
assert prov.kind == "local" and os.path.isdir(prov.root)
missions = P.find_missions(prov)
assert any("chernarusplus" in m for m in missions), missions
mrel = next(m for m in missions if "chernarusplus" in m)
files = P.resolve_files(prov, mrel)
assert "areaflags" in files and "cfglimits" in files
assert not P.missing_required(files), P.missing_required(files)
assert "economycore" in files and "types" in files and "mapgrouppos" in files
print(f"провайдер local: миссия {mrel}; ролей файлов {len(files)} "
      f"({', '.join(sorted(files))})")

# read_bytes/exists/mtime работают
assert prov.exists(f"{mrel}/areaflags.map")
raw = prov.read_bytes(f"{mrel}/areaflags.map")
assert len(raw) == 83_891_955 and prov.mtime(f"{mrel}/areaflags.map") > 0
print(f"read_bytes: areaflags {len(raw):,} байт")

# --- проект: материализация в служебную папку, чтение ядром ---
proj = P.Project(id="test1", name="Chernarus", provider_cfg={"kind": "local",
                 "root": SERVER_ROOT}, mission_name=mrel, files=files)
proj.save()
mdir = P.materialize(proj, prov)
assert os.path.isfile(os.path.join(mdir, "areaflags.map"))
assert os.path.isfile(os.path.join(mdir, "cfglimitsdefinition.xml"))
assert os.path.isfile(os.path.join(mdir, "db", "types.xml"))    # вложенный путь сохранён
af = read_areaflags(mdir)                        # ядро читает локальную копию
assert af.grid_x == 4096
print(f"материализация: {os.path.basename(mdir)}, ядро прочитало сетку {af.grid_x}²")

# конфиг сохранён и читается; пароль не утёк
loaded = P.Project.load("test1")
assert loaded.mission_name == mrel and loaded.files == files
assert "password" not in loaded.provider_cfg
assert P.list_projects()[0]["id"] == "test1"
print("конфиг проекта: сохранён и загружен")

# --- снапшот и Диф против него ---
assert not proj.has_snapshot()
P.make_snapshot(proj)
assert proj.has_snapshot()
snap_dir = P.snapshot_mission_dir(proj)
assert snap_dir and os.path.isfile(os.path.join(snap_dir, "areaflags.map"))
# правим рабочую копию -> Диф со снапшотом ловит изменение
import numpy as np

af.usage[af.usage.size // 2] |= np.uint32(1 << af.usages.index("Military"))
from core.writer import save_areaflags

save_areaflags(af, backup=False)
d = diff_maps(read_areaflags(snap_dir), read_areaflags(mdir))
assert d.changed_cells >= 1, "Диф против снапшота не увидел правку"
print(f"снапшот + Диф: изменённых ячеек {d.changed_cells}")

# удаление снапшота -> Диф невозможен
P.delete_snapshot(proj)
assert not proj.has_snapshot() and P.snapshot_mission_dir(proj) is None
print("удаление снапшота: Диф отключён")

# ручная загрузка снапшота из другого источника (ваниль как «сервер»)
VAN = r"D:\steam\steamapps\common\DayZServer\mpmissions"
if os.path.isdir(VAN):
    vprov = LocalProvider(VAN)
    P.load_snapshot_from(proj, vprov, "dayzOffline.chernarusplus")
    assert proj.has_snapshot()
    sd = P.snapshot_mission_dir(proj)
    assert os.path.isfile(os.path.join(sd, "areaflags.map"))
    print("ручной снапшот из ванили: загружен")

# --- единое место: данные, снапшот и сохранение — всё в appdata/projects/<id> ---
projw = P.Project(id="testwd", name="WD", provider_cfg={"kind": "local",
                  "root": SERVER_ROOT}, mission_name=mrel, files=files)
projw.save()
mdw = P.materialize(projw, prov)
# материализованная миссия лежит внутри папки проекта в appdata (никаких внешних папок)
assert str(mdw).startswith(str(projw.dir)), (mdw, projw.dir)
assert str(projw.dir).startswith(HOME)                         # HOME = M4_HOME = appdata
assert os.path.isfile(os.path.join(mdw, "areaflags.map"))
P.make_snapshot(projw)
assert str(P.snapshot_mission_dir(projw)).startswith(str(projw.dir))
# сохранение правки идёт туда же (af.source_path указывает в папку проекта)
afw = read_areaflags(mdw)
afw.usage[0] |= np.uint32(1 << afw.usages.index("Military"))
save_areaflags(afw, backup=False)
assert afw.source_path.startswith(str(projw.dir))
print(f"единое место: данные/снапшот/сохранение в {projw.dir}")

# --- SFTP: контракт без сети (paramiko может отсутствовать) ---
if sftp_available():
    p = make_provider({"kind": "sftp", "host": "h", "user": "u", "root": "/srv/dayz"})
    assert p.kind == "sftp" and p.label.startswith("sftp://u@h:22/srv/dayz")
    print("SFTP: провайдер создаётся, label ок")
else:
    try:
        make_provider({"kind": "sftp", "host": "h", "user": "u", "root": "/"})
        raise AssertionError("без paramiko SFTP должен падать понятной ошибкой")
    except ProviderError as e:
        assert "paramiko" in str(e)
    print("SFTP: paramiko нет — понятная ошибка")

shutil.rmtree(HOME, ignore_errors=True)
print("OK")
