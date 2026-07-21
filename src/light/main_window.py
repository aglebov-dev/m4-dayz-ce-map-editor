"""Лёгкое главное окно: поверх родительского добавляет слой проекта/провайдеров,
блокировку инструментов по наличию файлов (L3), Диф в двух режимах (L4) и экспорт
в проект BI (L5). Панели и карту переиспользуем из ui.main_window."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMessageBox, QToolButton
from PySide6.QtGui import QDesktopServices, QIcon

from core.building_index import load_index
from core.i18n import tr
from core.flags import (
    FlagError, add_usage, add_value, remove_usage, remove_value, write_cfglimits,
)
from core.paths import paths
from light import project as P
from light.gating import missing_for, tool_ok
from ui.diag import trace, log as _diag
from ui.main_window import MainWindow

# какие доки принадлежат какому инструменту (objectName -> tool).
# Всё требует минимум карту — без файлов проекта инструменты закрыты и заблокированы.
DOCK_TOOL = {
    "dock_layers": "map", "dock_inspector": "map", "dock_brush": "map",
    "dock_zones": "map", "dock_stats": "map",
    "dock_diff": "map", "dock_ce": "map",
    "dock_buildings": "objects", "dock_objects": "objects",   # слои зданий + инспектор
    "dock_items": "economy", "dock_loot": "economy",
    # территории убраны из лёгкого редактора: env/*.xml не материализуются (панель пуста)
}


class LightMainWindow(MainWindow):
    def __init__(self):
        super().__init__()
        self.project: P.Project | None = None
        self.setWindowTitle("m4 dayz ce map editor")

        # Иконка окна — из app_icon_high.ico
        icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "app_icon_high.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.setMinimumSize(640, 400)            # лёгкое окно свободно сжимается
        self.diff_panel.snapshot_requested.connect(self.diff_with_snapshot)  # дифф со снапшотом
        self._add_project_buttons()
        self._map_dock_buttons()
        self._light_layout_setup()
        # старт без проекта: инструменты закрыты и заблокированы, пока нет файлов
        self.apply_gating()

    def _light_layout_setup(self):
        from PySide6.QtCore import Qt

        # 1) панели прилипают только к бокам (не к верху/низу)
        side = Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        for dock in self._docks.values():
            dock.setAllowedAreas(side)
            dock.topLevelChanged.connect(
                lambda floating, d=dock: self._cap_floating(d) if floating else None)

        # 2) территории удалены — прячем док и его кнопку (через действие тулбара:
        #    hide() на виджете в тулбаре не убирает QWidgetAction)
        terr = self._docks.pop("dock_territories", None)
        if terr:
            terr.hide()
            terr.toggleViewAction().setEnabled(False)
            btn = self._dock_btn.pop("dock_territories", None)
            from PySide6.QtWidgets import QWidgetAction as _WA
            for act in self.tb_tools.actions():
                if isinstance(act, _WA) and act.defaultWidget() is btn:
                    act.setVisible(False)
                    break

        # 3) панель кисти не должна схлопываться в ноль
        self.brush_panel.setMinimumHeight(220)

        # 4) убрать лишние элементы тулбара: миссия задаётся проектом, подложка —
        #    при загрузке проекта. Прячем «Каталог», «Карта:»+комбобокс, «Background…».
        from PySide6.QtWidgets import QLabel, QWidgetAction
        main_toolbar = [t for t in self.findChildren(type(self.tb_tools))
                   if t.windowTitle() != "tools"][0]
        drop = {self.btn_workdir, self.cmb_mission, self.btn_background}
        for act in main_toolbar.actions():
            if isinstance(act, QWidgetAction):
                wdt = act.defaultWidget()
                if wdt in drop or isinstance(wdt, QLabel):   # QLabel тут только «Карта:»
                    act.setVisible(False)

    @trace
    def _cap_floating(self, dock):
        """Отцепили панель — высота не больше половины экрана. resize ОТКЛАДЫВАЕМ на
        следующий тик: менять геометрию дока прямо внутри topLevelChanged (Qt ещё
        перестраивает layout, мышь захвачена) — ре-энтрантность в раскладку доков и
        нативный abort (qFatal). После тика док уже верхнеуровневое окно — resize безопасен."""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, lambda d=dock: self._cap_floating_now(d))

    @trace
    def _cap_floating_now(self, dock):
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt as _Qt, QTimer
        if QApplication.mouseButtons() != _Qt.MouseButton.NoButton:
            _diag("defer _cap_floating_now (drag in progress)")
            QTimer.singleShot(60, lambda d=dock: self._cap_floating_now(d))
            return                                # пока драг — не трогаем геометрию
        try:
            if not dock.isFloating():             # успели вернуть в док — ничего не делаем
                return
        except RuntimeError:
            return                                # док уже разрушен
        scr = self.screen().availableGeometry() if self.screen() else None
        if not scr:
            return
        max_h = scr.height() // 2
        if dock.height() > max_h:
            dock.resize(dock.width(), max_h)

    # ---------- статистика/выделение: не открывать Спавн ----------

    def refresh_region_loot(self):
        """Заполняем сводку спавна по области, но НЕ открываем панель «Спавн» —
        выделение для статистики не должно поднимать чужую панель."""
        region = self.region_cells()
        b = self.buildings
        if region is None or b is None or self.types is None:
            return
        from core.stats import buildings_in_region, items_for_region
        idx = buildings_in_region(self.areaflags, b, region)
        rows = items_for_region(self.types, b, idx, self.bld_eff_u, self.bld_eff_v)
        self.loot_panel.show_region_items(len(idx), rows)   # без show()/raise_()

    def on_region_selected(self, x0, z0, x1, z1):
        super().on_region_selected(x0, z0, x1, z1)
        if self.dock_stats.toggleViewAction().isEnabled():
            self.dock_stats.show()
            self.dock_stats.raise_()          # фокус — на статистике, а не на Спавне

    def _load_territories(self, m):
        """Территории удалены из лёгкого редактора."""
        return

    # ---------- кнопки проекта ----------

    def _add_project_buttons(self):
        # первый тулбар (не «tools», где кнопки панелей)
        toolbars = [t for t in self.findChildren(type(self.tb_tools))
                    if t.windowTitle() != "tools"]
        main_toolbar = toolbars[0]
        first = main_toolbar.actions()[0]

        # СОХРАНИТЬ — яркая заметная кнопка слева
        self.button_save = QToolButton()
        self.button_save.setText(tr("toolbar.save"))
        self.button_save.setToolTip(tr("toolbar.save_tip"))
        self.button_save.clicked.connect(self.on_save)
        self.button_save.setStyleSheet(
            "QToolButton { background:#2e7d32; color:white; font-weight:bold;"
            " padding:3px 10px; border-radius:3px; }"
            "QToolButton:disabled { background:#c8c8c8; color:#888; }")
        self.button_save.setEnabled(False)
        main_toolbar.insertWidget(first, self.button_save)

        self.button_open = QToolButton()
        self.button_open.setText(tr("toolbar.open_project"))
        self.button_open.setToolTip(tr("toolbar.open_project_tip"))
        self.button_open.clicked.connect(self.open_project_dialog)
        main_toolbar.insertWidget(first, self.button_open)

        self.button_reload = QToolButton()
        self.button_reload.setText(tr("toolbar.reload_project"))
        self.button_reload.setToolTip(tr("toolbar.reload_project_tip"))
        self.button_reload.clicked.connect(self.reload_project)
        self.button_reload.setEnabled(False)
        main_toolbar.insertWidget(first, self.button_reload)

        self.button_snapshot = QToolButton()
        self.button_snapshot.setText(tr("toolbar.snapshot"))
        self.button_snapshot.setToolTip(tr("toolbar.snapshot_tip"))
        self.button_snapshot.clicked.connect(self.revert_to_snapshot)
        self.button_snapshot.setEnabled(False)
        main_toolbar.insertWidget(first, self.button_snapshot)
        main_toolbar.insertSeparator(first)

        # BI-экспорт — в общей группе с основными кнопками (а не у правого края)
        self.button_bi_export = QToolButton()
        self.button_bi_export.setText(tr("toolbar.bi_export"))
        self.button_bi_export.setToolTip(tr("toolbar.bi_export_tip"))
        self.button_bi_export.clicked.connect(self.export_to_bi)
        self.button_bi_export.setEnabled(False)
        main_toolbar.insertWidget(first, self.button_bi_export)

        # ПАПКА — открыть в проводнике папку с файлами текущей карты
        self.button_folder = QToolButton()
        self.button_folder.setText(tr("toolbar.folder"))
        self.button_folder.setToolTip(tr("toolbar.folder_tip"))
        self.button_folder.clicked.connect(self.open_map_folder)
        self.button_folder.setEnabled(False)
        main_toolbar.insertWidget(first, self.button_folder)

        # язык — сразу за BI (был у правого края за спейсером): всё идёт друг за другом
        lang_action = next((a for a in main_toolbar.actions()
                            if main_toolbar.widgetForAction(a) is self.cmb_lang), None)
        if lang_action is not None:
            main_toolbar.removeAction(lang_action)   # прячет виджет — вернём show() ниже
        new_lang_action = main_toolbar.insertWidget(first, self.cmb_lang)
        new_lang_action.setVisible(True)
        self.cmb_lang.setVisible(True)               # removeAction скрыл — показываем явно

        # добавление/удаление флагов — в панели «Слои» (заголовки секций и строки)
        self.layers_panel.allow_add_flag = True
        self.layers_panel.add_flag_requested.connect(self.add_flag)
        self.layers_panel.del_flag_requested.connect(self.del_flag)

    def _map_dock_buttons(self):
        """objectName -> кнопка-тогл (для блокировки инструмента)."""
        self._dock_btn = {}
        for w in self.tb_tools.findChildren(QToolButton):
            act = w.defaultAction() if hasattr(w, "defaultAction") else None
            if not act:
                continue
            for name, dock in self._docks.items():
                if dock.toggleViewAction() is act:
                    self._dock_btn[name] = w
                    break

    # ---------- проект ----------

    def open_project_dialog(self):
        # «Открыть проект» из редактора — то же приветственное окно, что и при старте
        from light.welcome_window import WelcomeWindow
        welcome = WelcomeWindow(self)
        if welcome.exec() and welcome.result_project:
            self.open_project(welcome.result_project)

    def open_project(self, proj: P.Project) -> bool:
        """Открыть проект. True — карта загружена; False — карты нет / файл повреждён
        (редактор показывать не нужно, сообщение уже показано)."""
        self._save_project_layout()              # раскладку ТЕКУЩЕГО проекта — перед сменой
        self.project = proj
        # ядро читает материализованную миссию; имя миссии — из config (плоская раскладка data/).
        # silent: своё понятное сообщение покажем ниже, без «миссии не найдены».
        self.load_workdir(proj.workdir, proj.mission_name, silent=True)
        if self.areaflags is None and self._open_map_only(proj):
            return True                          # проект-просмотрщик: подложка без миссии
        if self.areaflags is None:
            QMessageBox.warning(
                self, "Загрузка проекта",
                f"Не удалось открыть «{proj.name}»: карта не найдена или файл повреждён.")
            self.project = None
            return False
        self._restore_project_layout()           # раскладка панелей ЭТОГО проекта (если есть)
        self.apply_gating()                      # гейтинг — после раскладки (последнее слово)
        self.button_bi_export.setEnabled(True)
        self.button_folder.setEnabled(True)
        self.button_reload.setEnabled(True)
        has_snapshot = self.project.has_snapshot()
        self.button_snapshot.setEnabled(has_snapshot)
        self.button_save.setEnabled(True)        # карта загружена
        self.setWindowTitle(f"M4 DayZ CE Map Editor — {proj.name}")
        # Дифф: кнопка «Со снапшотом» + сразу подгружаем дифф со снапшотом (если он есть)
        self.diff_panel.set_snapshot_available(has_snapshot)
        if has_snapshot:
            self.diff_with_snapshot(raise_dock=False)
        return True

    # ---------- раскладка панелей: своя для каждого проекта ----------

    def _open_map_only(self, proj: P.Project) -> bool:
        """Открыть проект без миссии — только подложка. True, если получилось.

        Такие проекты создаёт источник «карта из PBO»: `files` пуст, поэтому `apply_gating`
        сам гасит все инструменты, а сохранять нечего. Миссию подделываем из meta.json
        пирамиды: `load_background` ждёт объект с `world`/`world_size`."""
        from light import tiles_store
        from core.workspace import Mission

        background = proj.background or ""
        if not background.startswith("tiles:"):
            return False
        world = background.split(":", 1)[1]
        meta = tiles_store.find(world)
        if not meta:
            return False
        mission = Mission(name=world, path="", world=world,
                          world_size=int(meta.world_size), has_areaflags=False)
        self.load_background(mission)
        self.lbl_af.setText(tr("af.missing"))
        self.apply_gating()
        self.button_save.setEnabled(False)       # править нечего — карты нет
        self.button_bi_export.setEnabled(False)
        self.button_snapshot.setEnabled(False)
        self.button_folder.setEnabled(True)
        self.button_reload.setEnabled(False)
        self.diff_panel.set_snapshot_available(False)
        self.setWindowTitle(f"M4 DayZ CE Map Editor — {proj.name} ({tr('src.mapfile_mode')})")
        return True

    def _save_project_layout(self):
        """Сохранить раскладку панелей текущего проекта (в его layout.json)."""
        if not self.project:
            return
        try:
            state = bytes(self.saveState().toBase64()).decode()
            P.save_layout(self.project, state)
        except Exception:
            pass

    def _restore_project_layout(self):
        """Восстановить раскладку панелей проекта. В offscreen пропускаем (детерминизм смоуков)."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        state = P.load_layout(self.project) if self.project else None
        if not state:
            return                               # нет своей раскладки — оставляем как есть
        from PySide6.QtCore import QByteArray
        try:
            self.restoreState(QByteArray.fromBase64(state.encode()))
        except Exception:
            pass

    def closeEvent(self, ev):
        self._save_project_layout()              # раскладку проекта — при выходе
        super().closeEvent(ev)                   # подтверждение правок + глобальная раскладка

    def diff_with_snapshot(self, raise_dock: bool = True):
        """Сравнить текущую карту со снапшотом проекта (исходным состоянием при создании)."""
        if not self.project or not self.project.has_snapshot():
            self.diff_panel.show_error("У проекта нет снапшота")
            return
        snapshot_dir = P.snapshot_mission_dir(self.project)
        if not snapshot_dir:
            self.diff_panel.show_error("Снапшот пуст")
            return
        self.load_diff(os.path.join(snapshot_dir, "areaflags.map"), raise_dock=raise_dock,
                       source=tr("diff.src_snapshot"))

    def reload_project(self):
        """Перечитать локальные файлы проекта (последнее сохранение на диске); сбрасывает
        несохранённые правки. Данные из источника заново НЕ тянем."""
        if not self.project:
            return
        if self._dirty_cells:
            ok = QMessageBox.question(
                self, "Перезагрузить",
                f"Несохранённых правок: {self._dirty_cells} ячеек. Перечитать проект "
                f"с диска (последнее сохранение) и потерять их?")
            if ok != QMessageBox.StandardButton.Yes:
                return
        self.open_project(self.project)          # перечитывает data/ проекта

    def open_map_folder(self):
        """Открыть в проводнике папку с файлами текущей карты (data/ проекта)."""
        if not self.project:
            return
        path = str(self.project.mission_dir)
        if os.path.isdir(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def revert_to_snapshot(self):
        """Откат к снапшоту: восстановить исходное состояние проекта (каким оно было при
        создании) из snapshot/ и перечитать. Теряются ВСЕ правки, включая сохранённые."""
        if not self.project:
            return
        if not self.project.has_snapshot():
            QMessageBox.information(self, "Снапшот", "У проекта нет снапшота.")
            return
        ok = QMessageBox.question(
            self, "Откат к снапшоту",
            "Вернуть проект к снапшоту (исходному состоянию при создании)? "
            "Все правки, включая сохранённые на диск, будут потеряны.")
        if ok != QMessageBox.StandardButton.Yes:
            return
        try:
            P.restore_snapshot(self.project)     # snapshot/ -> data/
        except Exception as e:
            QMessageBox.warning(self, "Откат к снапшоту", f"Не удалось: {e}")
            return
        self.open_project(self.project)

    def load_background(self, m):
        """Подложка: тайлы, ВЫБРАННЫЕ пользователем (мир из project.background), но только
        если размер их мира совпадает с текущей картой — иначе смена карты грузила бы
        чужую подложку и ломала масштаб. Имя мира миссии (m.world) для поиска не годится:
        у миссии-в-корне оно берётся из имени папки (DATA_SAMPLE≠chernarusplus)."""
        from light import tiles_store
        proj = getattr(self, "project", None)    # super().__init__ может звать до нас
        bg = proj.background if proj else ""
        # датасет зданий грузим вместе с подложкой; каноничный мир — из background
        # (m.world у миссии-в-корне = имя папки, для датасета не годится, как и для тайлов)
        canon_world = bg.split(":", 1)[1] if bg.startswith("tiles") and ":" in bg else m.world
        self.building_index = load_index(paths.buildings_roots(), canon_world)
        if bg.startswith("tiles"):
            world = bg.split(":", 1)[1] if ":" in bg else m.world
            meta = tiles_store.find(world)
            if meta and abs(meta.world_size - m.world_size) < 1:   # тайлы того же мира
                self.view.load_tiles(meta)
                self.lbl_bg.setText(f"подложка: тайлы {world}")
                return
        elif bg.startswith("image:"):
            path = bg.split(":", 1)[1]
            if os.path.isfile(path) and self.view.load_image(path, m.world_size):
                self.lbl_bg.setText(f"подложка: {os.path.basename(path)}")
                return
        # подложки нет — пустая сцена ТЕКУЩЕГО мира (не тянем чужие assets)
        self.view.clear_map()
        self.view._world_size = m.world_size     # иначе останется размер прошлой карты
        self.view.set_content_rect(m.world_size, m.world_size)
        self.view.add_border()
        self.view.fit_all()
        self.lbl_bg.setText("подложки нет")

    # ---------- добавление usage/value-флагов ----------

    def add_flag(self, kind: str):
        af = self.areaflags
        if af is None:
            return
        name, ok = QInputDialog.getText(
            self, f"Новый {kind}-флаг", f"Имя нового {kind}-флага:")
        if not ok:
            return
        try:
            (add_usage if kind == "usage" else add_value)(af, name)
            write_cfglimits(self.project.mission_dir, af)   # порядок битов на диск
        except FlagError as e:
            QMessageBox.warning(self, "Флаг", str(e))
            return
        self._repopulate_layers()
        # флаг записан в конфиг (движок его увидит), но бита в ячейке ему могло не достаться
        if kind == "usage" and name.strip() in af.unwritable_usages():
            if af.usage_bits < 32:
                answer = QMessageBox.question(
                    self, tr("af.usage_title"),
                    tr("af.widen_ask", bits=af.usage_bits, names=name.strip()),
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.Yes)
                if answer == QMessageBox.StandardButton.Yes and self._widen_usage(af):
                    self._repopulate_layers()
                    self.statusBar().showMessage(
                        f"Добавлен usage-флаг «{name.strip()}», ячейка расширена до 32 бит",
                        8000)
                    return
            QMessageBox.warning(
                self, "Флаг",
                f"Флаг «{name.strip()}» добавлен в cfglimitsdefinition.xml, но ячейка этой "
                f"карты хранит только {af.usage_bits} бит usage — рисовать его нельзя.")
            return
        self.statusBar().showMessage(
            f"Добавлен {kind}-флаг «{name.strip()}» (пустой слой — рисуйте кистью)", 8000)

    def del_flag(self, key: str):
        """Удалить usage/value-флаг (из данных и cfglimits). Биты выше сдвигаются."""
        af = self.areaflags
        if af is None or ":" not in key:
            return
        kind, name = key.split(":", 1)
        from PySide6.QtWidgets import QMessageBox
        cells = int(np.count_nonzero(
            (af.usage if kind == "usage" else af.tier)
            & (1 << (af.usages if kind == "usage" else af.values).index(name))))
        warn = (f"\n\nФлаг стоит в {cells:,} ячейках — они его потеряют."
                .replace(",", " ") if cells else "")
        if QMessageBox.question(
                self, "Удалить флаг",
                f"Удалить {kind}-флаг «{name}»?{warn}") != QMessageBox.StandardButton.Yes:
            return
        try:
            (remove_usage if kind == "usage" else remove_value)(af, name)
            write_cfglimits(self.project.mission_dir, af)
        except FlagError as e:
            QMessageBox.warning(self, "Флаг", str(e))
            return
        if self.brush_panel.layer_key() == key:
            self.view.set_brush_mode(False)
            self.brush_panel.sw_mode.setChecked(False)
        self.view.set_overlay(key, None)         # снять оверлей удалённого слоя
        self._layers_built.discard(key)
        self._repopulate_layers()
        self._after_edit()
        self.statusBar().showMessage(f"Удалён {kind}-флаг «{name}»", 6000)

    def _repopulate_layers(self):
        """Перестроить панель слоёв и список кисти под текущие usage/value (после
        добавления флага). Данные areaflags не трогаем — новый флаг пуст."""
        af = self.areaflags
        if af is None:
            return                                   # проект-просмотрщик: слоёв нет вовсе
        blocked = set(af.unwritable_usages())        # шире ячейки — кисти не отдаём
        self.layers.populate(af, tiers_on=False)     # презентер сам считает counts и цвета
        self.brush_panel.populate(
            [(f"tier:{n}", n, self.colors.color(f"tier:{n}")) for n in af.values],
            [(f"usage:{n}", n, self.colors.color(f"usage:{n}")) for n in af.usages
             if n not in blocked])

    def apply_gating(self):
        """Блокировать инструменты, чьих файлов нет; подсказать, каких именно."""
        files = self.project.files if self.project else {}
        for name, tool in DOCK_TOOL.items():
            dock = self._docks.get(name)
            if not dock:
                continue
            ok = tool_ok(files, tool)
            # блокируем САМО toggleViewAction — кнопка-тогл синхронизируется от него
            # (btn.setEnabled перетёрлось бы состоянием действия)
            act = dock.toggleViewAction()
            act.setEnabled(ok)
            if ok:
                act.setToolTip("")
            else:
                act.setToolTip("Недоступно — не загружено: "
                               + ", ".join(missing_for(files, tool)))
                dock.hide()

    # ---------- Диф со снапшотом (режим A) ----------

    # ---------- экспорт в BI (L5) ----------

    def export_to_bi(self):
        af = self.areaflags
        if not self.project or af is None:
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка назначения (проект BI)")
        if not folder:
            return
        from core.bi_export import export_project
        from light import tiles_store
        colors = {f"tier:{n}": self.layer_color(f"tier:{n}") for n in af.values}
        colors |= {f"usage:{n}": self.layer_color(f"usage:{n}") for n in af.usages}
        world = P.world_name(self.project.mission_name)
        cfg = os.path.join(self.project.mission_dir, "cfglimitsdefinition.xml")
        meta = tiles_store.find(world)           # подложка мира → map.png в проект
        bg_png = os.path.join(meta.root, "map.png") if meta else ""
        try:
            info = export_project(af, folder, cfglimits_src=cfg, colors=colors,
                                  world=world, background_png=bg_png)
        except Exception as e:
            QMessageBox.critical(self, "Экспорт", f"Не удалось: {e}")
            return
        bg = "map.png (подложка)\n" if info["background"] else ""
        QMessageBox.information(
            self, "Экспорт в BI",
            f"Готово: {folder}\n\nareaflags.map + cfglimitsdefinition.xml\n{bg}"
            f"TGA-слоёв: {info['layers']}\nпроект: {os.path.basename(info['xml'])}")
