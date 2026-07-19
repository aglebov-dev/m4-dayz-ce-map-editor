"""Окно открытия = конфигурация проекта (L1).

Выбор источника (папка / SFTP-корень сервера DayZ), миссии и КОНКРЕТНЫХ файлов, которые
пойдут в работу; видно, чего не хватает. По OK — материализация + (для нового проекта)
снапшот. Управление снапшотом — там же."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from core.paths import paths
from light import project as P
from light.gating import tool_status
from light.providers import ProviderError, make_provider, sftp_available


class ProjectConfigDialog(QDialog):
    """Возвращает готовый P.Project через .result_project (или None при отмене)."""

    def __init__(self, parent=None, existing: P.Project | None = None):
        super().__init__(parent)
        self.setWindowTitle("Configuration")
        self.resize(640, 640)
        self.result_project = None
        self._provider = None
        self._missions: list[str] = []
        self._files: dict = {}

        # --- источник ---
        self.cmb_kind = QComboBox()
        self.cmb_kind.addItem("FOLDER (DayZ server folder)", "local")
        if sftp_available(): self.cmb_kind.addItem("SFTP (DayZ server folder)", "sftp")
        self.cmb_kind.addItem("PROJECTS", "projects")
        self.cmb_kind.currentIndexChanged.connect(self._on_kind)

        # локальный
        self.ed_folder = QLineEdit()
        self.btn_folder = QPushButton("Open folder")
        self.btn_folder.clicked.connect(self._pick_folder)
        row_local = QHBoxLayout()
        row_local.addWidget(self.ed_folder, 1)
        row_local.addWidget(self.btn_folder)
        self.w_local = QWidget()
        fl = QFormLayout(self.w_local)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addRow("Root folder:", row_local) #_wrap(row_local)

        # sftp
        self.w_sftp = QWidget()
        fs = QFormLayout(self.w_sftp)
        fs.setContentsMargins(0, 0, 0, 0)
        self.ed_host = QLineEdit()
        self.sp_port = QSpinBox(); self.sp_port.setRange(1, 65535); self.sp_port.setValue(22)
        self.ed_user = QLineEdit()
        self.ed_pass = QLineEdit(); self.ed_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.ed_key = QLineEdit()
        self.ed_root = QLineEdit(); self.ed_root.setText("/")
        fs.addRow("Host:", self.ed_host)
        fs.addRow("Port:", self.sp_port)
        fs.addRow("User:", self.ed_user)
        fs.addRow("Password:", self.ed_pass)
        fs.addRow("Key", self.ed_key)
        fs.addRow("DayZ server folder", self.ed_root)
        self.w_sftp.hide()

        # projects
        self.projects_load_widget = QWidget()
        projects_load_layout = QFormLayout(self.projects_load_widget)
        # self.projects_load = QLineEdit()
        # projects_load_layout.addRow(self.projects_load)
        self.projects_load_combobox = QComboBox()


        # существующие проекты приложения (в appdata) — читаем напрямую из AppPaths,
        # а не через провайдер данных (провайдер — только для внешних источников)
        proot = paths.projects
        if proot.is_dir():
            for proj_dir in sorted(p for p in proot.iterdir() if p.is_dir()):
                data = proj_dir / "data"
                if not data.is_dir():
                    continue
                if any((m / "areaflags.map").exists()
                       or (m / "cfglimitsdefinition.xml").exists()
                       for m in data.iterdir() if m.is_dir()):
                    self.projects_load_combobox.addItem(proj_dir.name, proj_dir.name)


        projects_load_layout.addRow(self.projects_load_combobox)
        self.projects_load_combobox.hide()

        self.btn_connect = QPushButton("Open/Connect")
        self.btn_connect.clicked.connect(self._connect)

# Группа куда добавляем элементы для опций загрузки
        src = QGroupBox("Data source")
        sl = QVBoxLayout(src)
        sl.addWidget(self.cmb_kind)
        sl.addWidget(self.w_local)
        sl.addWidget(self.w_sftp)
        sl.addWidget(self.projects_load_widget)
        sl.addWidget(self.btn_connect)

        # --- миссия ---
        self.cmb_mission = QComboBox()
        self.cmb_mission.currentIndexChanged.connect(self._on_mission)
        self.miss = QGroupBox("Missions")
        ml = QVBoxLayout(self.miss)
        ml.addWidget(self.cmb_mission)

        # --- папка проекта (куда сохранять) ---
        self.project_name = QLineEdit() # инпут
        self.project_name.setPlaceholderText("Project name")
        self.wd = QGroupBox("Project") # контрол
        wl = QVBoxLayout(self.wd)
        wl.addWidget(self.project_name)
        

        # --- файлы (что пойдёт в работу) ---
        self.lst_files = QListWidget()
        self.lbl_tools = QLabel("")
        self.lbl_tools.setWordWrap(True)
        self.lbl_tools.setTextFormat(Qt.TextFormat.RichText)
        self.files = QGroupBox("Project files")
        fgl = QVBoxLayout(self.files)
        fgl.addWidget(QLabel("✔ loaded · ✖ failed"))
        fgl.addWidget(self.lst_files, 1)
        fgl.addWidget(self.lbl_tools)

        # --- подложка (спутник) ---
        self.cmb_bg = QComboBox()
        self.btn_bg_img = QPushButton("Select background…")
        self.btn_bg_img.clicked.connect(self._pick_bg_image)
        self.ed_game = QLineEdit()
        self.ed_game.setPlaceholderText("DayZ client folder")
        self.btn_game = QPushButton("Open folder")
        self.btn_game.clicked.connect(self._pick_game)
        self.btn_unpack = QPushButton("Unpack")
        self.btn_unpack.clicked.connect(self._unpack_bg)
        self.bg = QGroupBox("Satellite background")
        bl = QVBoxLayout(self.bg)
        bl.addWidget(QLabel("Scales to fit the world size from areaflags "
                            "(km are taken from the map - matching is automatic)."))
        row_bg = QHBoxLayout()
        row_bg.addWidget(QLabel("Source:"))
        row_bg.addWidget(self.cmb_bg, 1)
        row_bg.addWidget(self.btn_bg_img)
        bl.addLayout(row_bg)
        row_un = QHBoxLayout()
        row_un.addWidget(self.ed_game, 1)
        row_un.addWidget(self.btn_game)
        row_un.addWidget(self.btn_unpack)
        bl.addWidget(QLabel("Unpack the tile pyramid (satellite background) from the game files "
                            "(to the application's service folder):"))
        bl.addLayout(row_un)
        self._bg_image_path = ""
        self._refresh_backgrounds()

        # --- снапшот ---
        # self.lbl_snap = QLabel("")
        # self.btn_snap_del = QPushButton("Delete comparison snapshot")
        # self.btn_snap_del.clicked.connect(self._del_snapshot)
        # snap = QGroupBox("Snapshot for Dif")
        # sn = QVBoxLayout(snap)
        # sn.addWidget(QLabel("New project: a snapshot of the current data is created automatically"
        #                     "(standard Diff)."))
        # sn.addWidget(self.lbl_snap)
        # sn.addWidget(self.btn_snap_del)

        self.buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

        lay = QVBoxLayout(self)
        lay.addWidget(src)
        lay.addWidget(self.miss)
        lay.addWidget(self.wd)
        lay.addWidget(self.files, 1)
        lay.addWidget(self.bg)
        # lay.addWidget(snap)
        lay.addWidget(self.buttons)

        self._existing = existing
        if existing:
            self._prefill(existing)
        self._refresh_ok()

    # ---------- источник ----------

    def _on_kind(self):
        self.w_local.setVisible(False)
        self.projects_load_combobox.setVisible(False)
        self.w_sftp.setVisible(False)
        self.btn_connect.setVisible(False)

        self.miss.setDisabled(False)
        self.wd.setDisabled(False)
        self.files.setDisabled(False)
        self.bg.setDisabled(False)
        
        current = self.cmb_kind.currentData()
        if(current == "sftp"):
            self.w_sftp.setVisible(True)
            self.btn_connect.setVisible(True)
        if(current == "projects"):
            self.projects_load_combobox.setVisible(True)
            self.miss.setDisabled(True)
            self.wd.setDisabled(True)
            self.files.setDisabled(True)
            self.bg.setDisabled(True)
            # self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(True)
        if(current == "local"):
            self.w_local.setVisible(True)
            self.btn_connect.setVisible(True)

        self._refresh_ok()

    def _pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "The root folder of a server or mission")
        if d:
            self.ed_folder.setText(d)

    # def _pick_workdir(self):
    #     d = QFileDialog.getExistingDirectory(self, "Project folder (where to save files)")
    #     if d:
    #         self.project_name.setText(d)

    def _provider_cfg(self) -> dict:
        if self.cmb_kind.currentData() == "sftp":
            return {
                "kind": "sftp", 
                "host": self.ed_host.text().strip(),
                "port": self.sp_port.value(), 
                "user": self.ed_user.text().strip(),
                "password": self.ed_pass.text() or None,
                "key_path": self.ed_key.text().strip() or None,
                "root": self.ed_root.text().strip() or "/"
            }
        if self.cmb_kind.currentData() == "projects":
            return {
                "kind": "projects",
                "root": str(paths.projects),
            }
        
        return {
            "kind": "local", 
            "root": self.ed_folder.text().strip()
        }

    def _connect(self):
        try:
            self._provider = make_provider(self._provider_cfg())
            self._missions = P.find_missions(self._provider)
        except (ProviderError, KeyError, OSError) as e:
            QMessageBox.warning(self, "Source", f"Failed: {e}")
            self._provider = None
            self._missions = []
        self.cmb_mission.clear()
        if not self._missions:
            self.cmb_mission.addItem("missions not found", "")
        else:
            for m in self._missions:
                self.cmb_mission.addItem(m or "(root)", m)
        self._on_mission()

    # ---------- миссия и файлы ----------

    def _on_mission(self):
        self._files = {}
        self.lst_files.clear()
        if not self._provider or not self._missions:
            self._refresh_ok()
            return
        mrel = self.cmb_mission.currentData()
        if mrel is None:
            self._refresh_ok()
            return
        self._files = P.resolve_files(self._provider, mrel)
        for role in P.ROLES:
            here = role.key in self._files
            mark = "✔" if here else "✖"
            req = " (mandatory)" if role.required else ""
            it = QListWidgetItem(f"{mark}  {role.title}{req}")
            it.setForeground(Qt.GlobalColor.darkGreen if here else Qt.GlobalColor.gray)
            self.lst_files.addItem(it)
        self._update_tools()
        self._refresh_ok()

    def _update_tools(self):
        st = tool_status(self._files)
        names = {"map": "Map/Layers", "objects": "Objects", "economy": "Spawn",
                 "territories": "Territories"}
        parts = []
        for tool, s in st.items():
            if s["ok"]:
                parts.append(f"<span style='color:green'>✔ {names[tool]}</span>")
            else:
                parts.append(f"<span style='color:#b26a00'>✖ {names[tool]} "
                             f"(failed: {', '.join(s['missing'])})</span>")
        self.lbl_tools.setText("Tools: " + " · ".join(parts))

    # ---------- снапшот ----------

    def _prefill(self, proj: P.Project):
        cfg = proj.provider_cfg
        idx = self.cmb_kind.findData(cfg.get("kind", "local"))
        if idx >= 0:
            self.cmb_kind.setCurrentIndex(idx)
        if cfg.get("kind") == "sftp":
            self.ed_host.setText(cfg.get("host", ""))
            self.sp_port.setValue(int(cfg.get("port", 22)))
            self.ed_user.setText(cfg.get("user", ""))
            self.ed_root.setText(cfg.get("root", "/"))
        else:
            self.ed_folder.setText(cfg.get("root", ""))
        self.project_name.setText(proj.name)
        self._update_snapshot_label(proj)

    def _update_snapshot_label(self, proj: P.Project | None):
        if proj and proj.has_snapshot():
            self.lbl_snap.setText("<b>There is a snapshot</b> — Diff with snapshot is available.")
            self.btn_snap_del.setEnabled(True)
        else:
            self.lbl_snap.setText("No snapshot - Dif with snapshot is not available.")
            self.btn_snap_del.setEnabled(False)

    def _del_snapshot(self):
        if not self._existing:
            return
        ok = QMessageBox.question(
            self, "Delete snapshot",
            "Delete comparison snapshot?\n\nDiff with snapshot will stop working until"
            "do not recreate it or upload it manually.")
        if ok == QMessageBox.StandardButton.Yes:
            P.delete_snapshot(self._existing)
            self._update_snapshot_label(self._existing)

    # ---------- подложка ----------

    def _refresh_backgrounds(self, keep: str = ""):
        from light import tiles_store
        self.cmb_bg.blockSignals(True)
        self.cmb_bg.clear()
        self.cmb_bg.addItem("No", "")
        for world in tiles_store.available_worlds():
            self.cmb_bg.addItem(f"{world} (satellite)", f"tiles:{world}")
        if self._bg_image_path:
            self.cmb_bg.addItem(f"image: {os.path.basename(self._bg_image_path)}",
                                f"image:{self._bg_image_path}")
        want = keep or ""
        idx = self.cmb_bg.findData(want)
        self.cmb_bg.setCurrentIndex(max(0, idx))
        self.cmb_bg.blockSignals(False)

    def _pick_bg_image(self):
        p, _ = QFileDialog.getOpenFileName(
            self, "Background image", "",
            "Изображения (*.png *.jpg *.jpeg *.bmp)")
        if p:
            self._bg_image_path = p
            self._refresh_backgrounds(keep=f"image:{p}")

    def _pick_game(self):
        d = QFileDialog.getExistingDirectory(self, "DayZ folder")
        if d:
            self.ed_game.setText(d)

    def _unpack_bg(self):
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QApplication

        from light import tiles_unpack
        game = self.ed_game.text().strip()
        if not self._provider or self.cmb_mission.currentData() is None:
            QMessageBox.information(self, "Unpacking",
                                   "First, connect the source and select the mission.")
            return
        mrel = self.cmb_mission.currentData()
        world = P.world_name(mrel)                # 'chernarusplus' для PBO
        size = P.read_world_size(self._provider, mrel) or 15360
        if not tiles_unpack.available():
            QMessageBox.warning(
                self, "Unpacking",
                "You need .NET SDK 10+ (dotnet) and the ExtractSatMap.cs script.\n"
                f"Script: {tiles_unpack.script_path()}")
            return
        QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
        try:
            tiles_unpack.unpack(game, world, size)   # долго (минуты)
        except tiles_unpack.UnpackError as e:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Распаковка подложки", str(e))
            return
        QApplication.restoreOverrideCursor()
        self._refresh_backgrounds(keep=f"tiles:{world}")
        QMessageBox.information(self, "Распаковка",
                               f"Подложка мира «{world}» ({size} м) распакована.")

    # ---------- OK ----------

    def _refresh_ok(self):
        current = self.projects_load_combobox.currentData()
        ok2 = bool(self.projects_load_combobox.isVisible() and current)
        
        ok = bool(self._provider and self._files
                  and not P.missing_required(self._files))
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ok or ok2)

    def _accept(self):
        # грузим проект с диска
        if(self.cmb_kind.currentData() == "projects"):
            project_folder = self.projects_load_combobox.currentData()
            self.result_project = P.Project.load(project_folder)
            self.accept()
            return
        
        mission_name = self.cmb_mission.currentData() or "" # миссия в комбобоксе
        name = self.project_name.text().strip() or "map_project" # os.path.basename(mrel) or "project"
        # переиспользуем id ТОЛЬКО если это та же миссия из того же источника
        # (перенастройка текущего проекта). Другая миссия → НОВЫЙ проект со своей папкой —
        # иначе миссии копятся в одной data_dir и грузится не та карта.
        cfg = self._provider_cfg()

        # _existing это загрузка с открытого редактора !!!
        # same = (self._existing is not None
        #         and self._existing.mission_name == mission_name
        #         and self._existing.provider_cfg.get("kind") == cfg.get("kind")
        #         and self._existing.provider_cfg.get("root") == cfg.get("root"))
        pid = _new_id(name)
        proj = P.Project(
            id=pid, 
            name=name, 
            provider_cfg=cfg,
            mission_name=mission_name, 
            files=dict(self._files),
            background=self.cmb_bg.currentData() or "")
        try:
            proj.save()
            P.materialize(proj, self._provider)
            P.make_snapshot(proj)
        except Exception as e:
            QMessageBox.critical(self, "Проект", f"Не удалось подготовить проект: {e}")
            return
        self.result_project = proj
        self.accept()


def _wrap(layout) -> QWidget:
    w = QWidget()
    w.setLayout(layout)
    return w


def _new_id(name: str) -> str:
    base = "".join(c if c.isalnum() else "_" for c in name)[:32] or "proj"
    pid, n = base, 2
    while paths.project(pid).is_dir():
        pid = f"{base}_{n}"; n += 1
    return pid
