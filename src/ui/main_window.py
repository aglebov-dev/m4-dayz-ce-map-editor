"""Главное окно: рабочий каталог, выбор карты, подложка."""
from __future__ import annotations

import os

import numpy as np
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDockWidget, QFileDialog, QFrame, QLabel, QMainWindow,
    QMessageBox, QPushButton, QScrollArea, QSizePolicy, QToolBar, QToolButton,
    QWidget,
)

from core.paths import paths

# насколько узким можно сделать док, подтянув его к краю окна
DOCK_MIN_WIDTH = 90

from core import i18n
from core.areaflags import read_areaflags
from core.brush import History, plane_array, stroke
from core.diff import DiffError, diff_maps, diff_planes
from core.export import mask_rgba
from core.groups import read_buildings
from core.shapes import fill_ellipse, fill_polygon, fill_rect
from core.i18n import tr
from core.tiles import find_tiles
from core.types import instances_for_item, items_for_building, read_types

from core.stats import (
    buildings_in_region, items_for_region, map_stats, region_from_world,
)
from core.ce_project import layer_mask, read_project, water_mask
from core.territories import read_territories
from core.workspace import Mission, Settings, scan_workdir
from core.writer import FileChangedError, WriteError, save_areaflags
from core.zones import find_zones
from ui.brush_panel import BrushPanel
from ui.ce_project_panel import CeProjectPanel
from ui.flow_layout import FlowLayout
from ui.diff_panel import DiffPanel
from ui.inspector_panel import InspectorPanel
from ui.items_panel import ItemsPanel
from ui.layers_panel import LayersPanel, TerritoriesPanel
from ui.app_bus import AppBus
from ui.layers_presenter import LayersPresenter
from ui.zones_presenter import ZonesPresenter
from ui.inspector_presenter import InspectorPresenter
from ui.buildings_presenter import BuildingsPresenter
from ui.items_presenter import ItemsPresenter
from ui.territories_presenter import TerritoriesPresenter
from common.buildings import BuildingsModel
from core.building_index import load_index
from common.layer_colors import LayerColors
from ui.map_view import MapView
from ui.overlays import (
    build_diff_pixmap, rgba_to_pixmap, tier_color, usage_color,
)


def _rgba_pixmap(rgba):
    return rgba_to_pixmap(rgba)
from ui.stats_panel import StatsPanel
from ui.zones_panel import ZonesPanel

class MainWindow(QMainWindow):
    language_changed = Signal(str)               # окно пересоздаётся с новой локалью (app.py)

    def __init__(self):
        super().__init__()
        paths.ensure(paths.appdata)
        self.settings = Settings(str(paths.settings_file))
        i18n.load(self.settings.lang)            # ДО построения UI
        self.setWindowTitle(tr("app.title"))
        self.resize(1280, 860)
        # панели можно стыковать рядом друг с другом (вложенные сплиты) и таскать группой
        self.setDockOptions(
            QMainWindow.DockOption.AnimatedDocks
            | QMainWindow.DockOption.AllowNestedDocks
            | QMainWindow.DockOption.AllowTabbedDocks
            | QMainWindow.DockOption.GroupedDragging)
        self.buildings = None
        self.types = None
        self.missions: list[Mission] = []
        self.areaflags = None

        tb = QToolBar("Основное")
        tb.setMovable(False)
        self.addToolBar(tb)

        self.btn_workdir = QPushButton(tr("toolbar.workdir_btn"))
        self.btn_workdir.clicked.connect(self.choose_workdir)
        tb.addWidget(self.btn_workdir)

        tb.addWidget(QLabel(tr("toolbar.map")))
        self.cmb_mission = QComboBox()
        self.cmb_mission.setMinimumWidth(360)
        self.cmb_mission.currentIndexChanged.connect(self.on_mission_selected)
        tb.addWidget(self.cmb_mission)

        self.btn_background = QPushButton(tr("toolbar.background"))
        self.btn_background.clicked.connect(self.choose_background)
        self.btn_background.setEnabled(False)
        tb.addWidget(self.btn_background)

        # выделение области переехало в панель «Статистика» (тогл-кнопка); экспорт удалён

        # язык — в конец первого ряда: во втором ряду теперь десять кнопок панелей,
        # и он переполнялся (кнопки уезжали в скрытое меню)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(spacer)
        self.cmb_lang = QComboBox()
        self.cmb_lang.addItems(i18n.available())
        self.cmb_lang.setCurrentText(self.settings.lang)
        self.cmb_lang.setToolTip(tr("lang.tip"))
        self.cmb_lang.currentTextChanged.connect(self.on_lang_changed)
        tb.addWidget(self.cmb_lang)

        self.view = MapView(self)
        self.setCentralWidget(self.view)
        self.view.cursor_world.connect(self.on_cursor)

        # плашки подложки и areaflags — в статус-баре, а не в тулбаре: это статусная
        # информация, а длинными текстами они переполняли ряд кнопок
        self.lbl_bg = QLabel("")
        self.statusBar().addWidget(self.lbl_bg)
        self.lbl_af = QLabel("")
        self.statusBar().addWidget(self.lbl_af)

        self.status_coords = QLabel("—")
        self.statusBar().addPermanentWidget(self.status_coords)

        # общий подбор цвета слоёв (для всех фич) + шина кросс-фичевых событий
        self._terr_colors: dict[str, tuple[int, int, int]] = {}
        self.bus = AppBus(self)
        self.colors = LayerColors(
            settings=self.settings, mission=self.current_mission,
            areaflags=lambda: getattr(self, "areaflags", None),
            territory_colors=self._terr_colors)

        # === фича «Слои» (tier/usage): вся логика в ui/layers_presenter.py ===
        # Презентер владеет своей панелью и доком; MainWindow только расставляет доки.
        self.layers = LayersPresenter(
            self, view=self.view, colors=self.colors, settings=self.settings,
            mission=self.current_mission, bus=self.bus, wrap=self._dock_widget)
        self.layers_panel = self.layers.panel        # алиас для смежного кода (кисть/инспектор)
        self.dock_layers = self.layers.dock          # для реестра доков и расстановки

        # === фича «Здания» (слои по флагам + инспектор здания + спавн; режим точки/контур/оба) ===
        # бывшая фича «Объекты» слилась сюда: ui/buildings_presenter.py
        self.buildings_feature = BuildingsPresenter(
            self, view=self.view, colors=self.colors, settings=self.settings,
            mission=self.current_mission, bus=self.bus, wrap=self._dock_widget)
        self.objects = self.buildings_feature            # алиас: клик по карте, is_active и т.п.
        self.loot_panel = self.buildings_feature.loot_panel   # алиас: нужен для лута по области
        self.building_index = None                       # core.building_index.BuildingIndex | None
        self.dock_buildings = self.buildings_feature.dock
        self.dock_objects = self.buildings_feature.dock_inspector
        self.dock_loot = self.buildings_feature.dock_loot

        # === фича «Территории» (круги животных): ui/territories_presenter.py ===
        self.territories = TerritoriesPresenter(
            self, view=self.view, colors=self.colors, settings=self.settings,
            mission=self.current_mission, territory_colors=self._terr_colors,
            wrap=self._dock_widget)
        self.territories_panel = self.territories.panel   # алиас (light прячет этот док)
        self.dock_territories = self.territories.dock

        # панели информации — СПРАВА. === фича «Зоны»: вся логика в ui/zones_presenter.py ===
        self.zones = ZonesPresenter(
            self, view=self.view, colors=self.colors, bus=self.bus,
            areaflags=lambda: getattr(self, "areaflags", None),
            is_layer_visible=self.layers.is_visible, wrap=self._dock_widget)
        self.dock_zones = self.zones.dock

        # === фича «Инспектор слоёв»: вся логика в ui/inspector_presenter.py ===
        self.inspector = InspectorPresenter(
            self, view=self.view, bus=self.bus, wrap=self._dock_widget)
        self.inspector_panel = self.inspector.panel   # алиас на сам виджет
        self.dock_inspector = self.inspector.dock
        # клик по карте обслуживает и инспектор слоёв, и объектов — общий диспетчер
        self.view.clicked_world.connect(self.on_map_clicked)

        # панель статистики: площади флагов по карте / по выделенной области
        self.stats_panel = StatsPanel(self)
        self.stats_panel.select_toggled.connect(self.on_select_toggled)  # тогл выделения области
        self.stats_panel.flag_clicked.connect(self.bus.layer_selected)  # клик по флагу = выбрать слой
        self.dock_stats = QDockWidget(tr("dock.stats"), self)
        self.dock_stats.setObjectName("dock_stats")
        self.dock_stats.setWidget(self._dock_widget(self.stats_panel))
        # сводка считается по всей карте (~100 мс) — во время рисования коалесцируем
        self._stats_dirty = False

        # === Шина слоёв (AppBus): что осталось на MainWindow ===
        # авто-показ -> layers_presenter; показ и цвет зон -> zones_presenter; тут — только кисть
        self.bus.layer_selected.connect(self.on_layer_selected)   # выбор -> слой рисования кисти (ниже)
        self._stats_timer = QTimer(self)
        self._stats_timer.setSingleShot(True)
        self._stats_timer.setInterval(250)
        self._stats_timer.timeout.connect(self._do_refresh_stats)
        self.dock_stats.visibilityChanged.connect(self._on_stats_visible)
        self.view.region_selected.connect(self.on_region_selected)
        self.view.region_cleared.connect(self.on_clear_region)

        # панель кисти — инструментарий, к слоям слева
        self.brush_panel = BrushPanel(self)
        self.brush_panel.mode_toggled.connect(self.on_brush_mode)
        self.brush_panel.tool_changed.connect(self.view.set_tool)
        self.brush_panel.apply_shape.connect(self.view.commit_shape)
        self.brush_panel.cancel_shape.connect(self.view.cancel_shape)
        self.view.shape_committed.connect(self.on_shape_committed)
        self.view.shape_state.connect(self.brush_panel.set_shape_ready)
        self.brush_panel.layer_changed.connect(self.on_brush_layer)
        self.brush_panel.radius_changed.connect(self.view.set_brush_radius)
        self.brush_panel.erase_toggled.connect(self.on_brush_erase)
        self.brush_panel.undo_requested.connect(self.on_undo)
        self.brush_panel.redo_requested.connect(self.on_redo)
        self.brush_panel.save_requested.connect(self.on_save)
        self.dock_brush = QDockWidget(tr("dock.brush"), self)
        self.dock_brush.setObjectName("dock_brush")
        self.dock_brush.setWidget(self._dock_widget(self.brush_panel))
        self.view.stroke_started.connect(self.on_stroke_started)
        self.view.paint_world.connect(self.on_paint)
        self.view.stroke_finished.connect(self.on_stroke_finished)
        self.history = History()
        self._stroke: list = []                  # патчи текущего мазка
        self._last_paint = None                  # прошлая точка мазка (для отрезка)
        self._erase = False
        self._dirty_cells = 0                    # ячеек разошлось с файлом на диске

        # панель проекта CE Tool: импорт TGA-слоёв (вода/суша, сравнение со слоями)
        self.ce_panel = CeProjectPanel(self)
        self.ce_panel.load_requested.connect(self.choose_ce_project)
        self.ce_panel.water_toggled.connect(self.on_ce_water)
        self.ce_panel.layer_clicked.connect(self.on_ce_layer)
        self.ce_panel.clear_overlay.connect(self.on_ce_clear_overlay)
        self.dock_ce = QDockWidget(tr("dock.ce"), self)
        self.dock_ce.setObjectName("dock_ce")
        self.dock_ce.setWidget(self._dock_widget(self.ce_panel))
        self.ce_project = None
        self.ce_water = None                     # bool-грид воды (для инспектора/оверлея)
        self._ce_layer_key = None

        # панель диффа: текущая карта против другого areaflags.map
        self.diff_panel = DiffPanel(self)
        self.diff_panel.load_requested.connect(self.choose_diff_file)
        self.diff_panel.flag_clicked.connect(self.on_diff_flag)
        self.diff_panel.clear_requested.connect(self.on_diff_clear)
        self.dock_diff = QDockWidget(tr("dock.diff"), self)
        self.dock_diff.setObjectName("dock_diff")
        self.dock_diff.setWidget(self._dock_widget(self.diff_panel))
        self.diff_other = None                   # AreaFlags второго среза
        self._diff_key = None                    # какой флаг сейчас на карте

        # панель Items: весь справочник типов, мультивыбор -> здания на карте
        # === фича «Предметы» (обратный матчинг): ui/items_presenter.py ===
        self.items = ItemsPresenter(
            self, view=self.view, buildings=lambda: self.buildings_model,
            building_opacity=self.objects.opacity, wrap=self._dock_widget)
        self.dock_items = self.items.dock

        self._default_dock_layout()

        # ПРАВИЛО UI: каждая панель регистрируется здесь — тогл-кнопка появляется сама.
        # Обычный тулбар: лишние кнопки уходят в меню «»» (лёгкое окно должно свободно
        # сжиматься; FlowLayout-хост фиксировал ширину/высоту и ломал ресайз).
        self.addToolBarBreak()
        self.tb_tools = QToolBar("tools")
        self.tb_tools.setMovable(False)
        self.addToolBar(self.tb_tools)
        for dock in (self.dock_layers, self.dock_buildings,
                     self.dock_brush, self.dock_territories, self.dock_items,
                     self.dock_zones, self.dock_stats, self.dock_diff, self.dock_ce,
                     self.dock_inspector, self.dock_objects, self.dock_loot):
            self._register_dock_button(dock)



        # undo/redo с клавиатуры — привычнее кнопок в панели
        for seq, slot in ((QKeySequence.StandardKey.Undo, self.on_undo),
                          (QKeySequence.StandardKey.Redo, self.on_redo)):
            act = QAction(self)
            act.setShortcut(seq)
            act.triggered.connect(slot)
            self.addAction(act)

        self._restore_ui_state()
        # Прошлый проект при старте НЕ загружаем — загрузку ведёт приветственное окно
        # (иначе битый/устаревший workdir сразу даёт ошибку).

    def _dock_widget(self, panel: QWidget) -> QWidget:
        """Содержимое дока — в область прокрутки: иначе минимальную ширину панели
        диктует её содержимое (у «Предметов» это было 572 px), и док не подтянуть
        к краю окна. Теперь узкий док просто прокручивается по горизонтали."""
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.Shape.NoFrame)
        sa.setWidget(panel)
        sa.setMinimumWidth(DOCK_MIN_WIDTH)
        return sa

    def _default_dock_layout(self):
        """Компоновка по умолчанию: слева Слои над Зданиями; справа сверху вкладки
        Предметы|Спавн|Зоны, снизу вкладки Инспектор здания|Инспектор слоёв."""
        L, R = Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.RightDockWidgetArea
        V = Qt.Orientation.Vertical
        self.addDockWidget(L, self.dock_layers)
        self.addDockWidget(L, self.dock_buildings)
        self.splitDockWidget(self.dock_layers, self.dock_buildings, V)
        self.tabifyDockWidget(self.dock_buildings, self.dock_brush)
        self.tabifyDockWidget(self.dock_brush, self.dock_territories)
        self.addDockWidget(R, self.dock_items)
        self.addDockWidget(R, self.dock_objects)
        self.splitDockWidget(self.dock_items, self.dock_objects, V)
        self.tabifyDockWidget(self.dock_items, self.dock_loot)
        self.tabifyDockWidget(self.dock_loot, self.dock_zones)
        self.tabifyDockWidget(self.dock_zones, self.dock_stats)
        self.tabifyDockWidget(self.dock_stats, self.dock_diff)
        self.tabifyDockWidget(self.dock_diff, self.dock_ce)
        self.tabifyDockWidget(self.dock_objects, self.dock_inspector)
        self.resizeDocks([self.dock_layers, self.dock_items], [280, 330],
                         Qt.Orientation.Horizontal)
        self.resizeDocks([self.dock_layers, self.dock_buildings], [400, 400], V)
        self.resizeDocks([self.dock_items, self.dock_objects], [440, 340], V)
        self.dock_items.raise_()
        self.dock_objects.raise_()

    def _restore_ui_state(self):
        """Раскладка прошлого запуска; не восстановилась — все панели выключены.
        В offscreen-тестах не применяется (детерминизм смоуков)."""
        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        st = self.settings.data.get("ui_state")
        if not st:
            return                               # первый запуск — компоновка по умолчанию
        from PySide6.QtCore import QByteArray
        try:
            geo = self.settings.data.get("ui_geometry")
            if geo:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
            ok = self.restoreState(QByteArray.fromBase64(st.encode()))
        except Exception:
            ok = False
        if not ok:
            for d in self._docks.values():
                d.close()

    def showEvent(self, ev):
        """Карта грузится в конструкторе — там панели ещё невидимы, и сводка осталась
        отложенной. visibilityChanged при показе ОКНА не приходит, так что досчитываем
        здесь, иначе таблица стояла бы пустой до первого клика по вкладке."""
        super().showEvent(ev)
        QTimer.singleShot(0, lambda: self._stats_dirty and self.refresh_stats(now=True))

    def closeEvent(self, ev):
        if getattr(self, "_dirty_cells", 0):     # несохранённые правки — спросить
            ok = QMessageBox.question(
                self, tr("exit.title"),
                tr("exit.unsaved", n=f"{self._dirty_cells:,}".replace(",", " ")),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if ok != QMessageBox.StandardButton.Yes:
                ev.ignore()
                return
        try:
            self.settings.data["ui_state"] = bytes(
                self.saveState().toBase64()).decode()
            self.settings.data["ui_geometry"] = bytes(
                self.saveGeometry().toBase64()).decode()
            self.settings.save()
        except Exception:
            pass
        super().closeEvent(ev)

    def _register_dock_button(self, dock: QDockWidget):
        """Тогл-кнопка панели в тулбаре инструментов. ОБЯЗАТЕЛЬНО для каждой новой панели."""
        if not hasattr(self, "_docks"):
            self._docks: dict[str, QDockWidget] = {}
            self._dock_state: dict[str, dict] = {}
        self._docks[dock.objectName()] = dock
        btn = QToolButton()
        act = dock.toggleViewAction()
        btn.setDefaultAction(act)                       # чекается сам, синхронно с доком
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        # перед скрытием запоминаем, где док жил (вкладки/область/плавание)
        dock.visibilityChanged.connect(
            lambda vis, d=dock: None if vis else self._remember_dock_state(d))
        # при включении тоглом восстанавливаем состояние; не вышло — плавающим у центра
        # (именно triggered: только клик пользователя, не программная раскладка)
        act.triggered.connect(
            lambda on, d=dock: self._ensure_dock_visible(d) if on else None)
        self.tb_tools.addWidget(btn)

    def _remember_dock_state(self, dock: QDockWidget):
        from PySide6.QtCore import QRect
        try:
            self._dock_state[dock.objectName()] = {
                "floating": dock.isFloating(),
                "geo": QRect(dock.frameGeometry() if dock.isFloating()
                             else dock.geometry()),
                "area": self.dockWidgetArea(dock),
                "tabs": [x.objectName() for x in self.tabifiedDockWidgets(dock)],
            }
        except RuntimeError:
            pass                                 # окно уже разрушается (выход из приложения)

    def _on_screen(self, rect) -> bool:
        from PySide6.QtGui import QGuiApplication
        return any(rect.intersects(s.availableGeometry())
                   for s in QGuiApplication.screens())

    def _ensure_dock_visible(self, dock: QDockWidget):
        """Открытый тоглом док возвращается в свою группу вкладок; ПЛАВАЮЩИЙ без валидного
        сохранённого положения — по центру окна (общее правило `_float_centered`)."""
        st = self._dock_state.get(dock.objectName())
        restored = False
        if st and not st["floating"]:                # вернуть в ту же группу вкладок / область
            partner = next(
                (self._docks[n] for n in st["tabs"]
                 if n in self._docks and self._docks[n].isVisible()
                 and not self._docks[n].isFloating()), None)
            if partner is not None:
                self.tabifyDockWidget(partner, dock)
                restored = True
            elif st["area"] != Qt.DockWidgetArea.NoDockWidgetArea:
                self.addDockWidget(st["area"], dock)
                restored = True
        elif st and st["floating"] and self._on_screen(st["geo"]):
            dock.setFloating(True)
            dock.setGeometry(st["geo"])              # своё плавающее место, если на экране
            restored = True
        if not restored:
            self._float_centered(dock)               # нет положения -> по центру окна
        dock.show()
        dock.raise_()
        # Qt показывает док ПОСЛЕ этого (по устаревшей геометрии — иногда за пределами окна),
        # и таб-док может встать позади активной вкладки. Проверяем/чиним отложенно.
        QTimer.singleShot(0, lambda d=dock: self._place_dock_if_needed(d))

    def _place_dock_if_needed(self, dock: QDockWidget):
        """После показа Qt: плавающий док вне экрана — вернуть по центру окна; поднять."""
        try:
            if dock.isFloating() and not self._on_screen(dock.frameGeometry()):
                self._float_centered(dock)
            dock.show()
            dock.raise_()
        except RuntimeError:
            pass                                     # окно уже разрушено

    def _float_centered(self, dock: QDockWidget):
        """ОБЩЕЕ ПРАВИЛО для доков без сохранённого положения: плавающее окно по центру
        главного окна, с небольшим смещением ВЛЕВО, высотой ~300 px — всегда видно."""
        dock.setFloating(True)
        width = max(320, dock.width())
        height = 300
        center = self.frameGeometry().center()
        dock.setGeometry(center.x() - width // 2 - 60, center.y() - height // 2,
                         width, height)

    # ---------- рабочий каталог ----------

    def choose_workdir(self):
        d = QFileDialog.getExistingDirectory(
            self, tr("dlg.workdir_title"), self.settings.workdir or "D:\\")
        if d:
            self.load_workdir(d)

    def load_workdir(self, d: str, mission_name: str = "", silent: bool = False):
        d = os.fspath(d)                         # принимаем Path (project.workdir) и str
        self.missions = scan_workdir(d, mission_name)   # имя миссии из config (плоская раскладка)
        self.settings.workdir = d
        self.settings.save()
        self.btn_workdir.setText(
            tr("toolbar.workdir_named", name=os.path.basename(os.path.normpath(d)) or d))
        self.cmb_mission.blockSignals(True)
        self.cmb_mission.clear()
        for m in self.missions:
            self.cmb_mission.addItem(
                tr("mission.title", name=m.name, world=m.world, size=m.world_size), m)
        self.cmb_mission.blockSignals(False)
        if not self.missions:
            if not silent:                       # тихий режим: сообщение покажет вызывающий
                QMessageBox.warning(self, tr("dlg.no_missions_title"), tr("dlg.no_missions_text"))
            return
        idx = 0
        for i, m in enumerate(self.missions):
            if m.name == self.settings.last_mission:
                idx = i
                break
        self.cmb_mission.setCurrentIndex(idx)
        if idx == 0:
            self.on_mission_selected(0)

    # ---------- карта ----------

    def current_mission(self) -> Mission | None:
        return self.cmb_mission.currentData()

    def on_mission_selected(self, _i: int):
        m = self.current_mission()
        if not m:
            return
        self.settings.last_mission = m.name
        self.settings.save()
        self.btn_background.setEnabled(True)
        self.load_background(m)
        self.load_areaflags(m)

    def load_background(self, m: Mission):
        # датасет зданий (footprint) грузим вместе с подложкой — оба bundled и по миру
        self.building_index = load_index(paths.assets_buildings, m.world)
        # 1) спутниковые тайлы
        meta = find_tiles(paths.assets_tiles, m.world)
        if meta:
            self.view.load_tiles(meta)
            self.lbl_bg.setText(tr("bg.tiles", world=m.world, max=meta.max_zoom))
            return
        # 2) сохранённый выбор пользователя
        saved = self.settings.background_for(m.name)
        if saved and os.path.isfile(saved) and self.view.load_image(saved, m.world_size):
            self.lbl_bg.setText(tr("bg.image", file=os.path.basename(saved)))
            return
        # 3) нет ничего — пустая сцена мира
        self.view.clear_map()
        self.view.set_content_rect(m.world_size, m.world_size)
        self.view.add_border()
        self.view.fit_all()
        self.lbl_bg.setText(tr("bg.none"))

    def choose_background(self):
        m = self.current_mission()
        if not m:
            return
        p, _ = QFileDialog.getOpenFileName(
            self, tr("dlg.bg_title", name=m.name), "", tr("dlg.bg_filter"))
        if not p:
            return
        if self.view.load_image(p, m.world_size):
            self.settings.set_background(m.name, p)
            self.settings.save()
            self.lbl_bg.setText(tr("bg.image", file=os.path.basename(p)))
        else:
            QMessageBox.warning(self, tr("dlg.error"), tr("dlg.bg_load_failed"))

    # ---------- areaflags / оверлей тиров ----------

    def load_areaflags(self, m: Mission):
        self.areaflags = None
        self.buildings_model = None              # common.buildings.BuildingsModel | None
        self.buildings = None                    # алиасы модели (пока читают статистика/light)
        self.types = None
        self.bld_eff_u = None
        self.bld_eff_v = None
        self.view.clear_buildings()
        self.view.clear_footprints()
        self.view.clear_territories()
        self.territories.clear()
        self.items.clear()
        self.view.clear_overlays()
        self.layers.clear()                      # презентер слоёв: панель + кэш пиксмапов
        self.buildings_feature.clear()           # слои зданий + инспектор здания + спавн
        self.zones.clear()
        self.view.clear_region()                 # выделение принадлежит прошлой карте
        self.stats_panel.clear()
        self.on_diff_clear()                     # дифф считался против прошлой карты
        self.on_ce_clear_overlay()               # оверлей слоя проекта — от прошлой карты
        self.view.set_overlay("ce:water", None)
        self.ce_project = None
        self.ce_water = None
        self.ce_panel.clear()
        self.brush_panel.clear()                 # история правок — от прошлой карты
        self.history.clear()
        self._stroke = []
        self._dirty_cells = 0
        self._af_orig = None                     # снимок файла для счётчика правок
        self.lbl_af.setStyleSheet("")
        if not m.has_areaflags:
            self.lbl_af.setText(tr("af.missing"))
            return
        if not os.path.isfile(os.path.join(m.path, "cfglimitsdefinition.xml")):
            self.lbl_af.setText(tr("af.no_limits"))
            return
        try:
            self.areaflags = read_areaflags(m.path)
        except Exception as e:
            self.lbl_af.setText(tr("af.error", err=e))
            self.lbl_af.setStyleSheet("color: #c62828;")
            return
        af = self.areaflags
        # снимок «как на диске»: по нему считается, сколько ячеек развела кисть
        self._af_orig = (af.usage.copy(), af.tier.copy())
        # модель зданий (Qt-free) — источник для инспектора объектов/спавна/предметов
        self.buildings_model = BuildingsModel.build(m.path, af)
        model = self.buildings_model
        self.buildings = model.buildings if model else None       # алиасы (статистика/light)
        self.bld_eff_u = model.eff_u if model else None
        self.bld_eff_v = model.eff_v if model else None
        self.types = model.types if model else None
        if model and self.types is not None:
            self.items.populate(self.types)
        self.layers.populate(af)                 # презентер сам считает counts и цвета
        self.buildings_feature.populate(af, model, self.building_index)   # слои + инспектор
        self._load_territories(m)
        self.brush_panel.populate([(f"tier:{n}", n) for n in af.values]
                                  + [(f"usage:{n}", n) for n in af.usages])
        self.refresh_stats(now=True)             # карта загружена — сводка по всей карте
        if af.repaired_crlf:
            self.lbl_af.setText(tr("af.repaired", n=af.repaired_crlf))
            self.lbl_af.setStyleSheet("color: #2e7d32;")
        else:
            self.lbl_af.setText(tr("af.v1"))

    def layer_color(self, key: str) -> tuple[int, int, int]:
        """Совместимость: логика подбора вынесена в common.layer_colors.LayerColors."""
        return self.colors.color(key)

    def _load_territories(self, m):
        """Хук загрузки территорий (в лёгком редакторе переопределён в no-op)."""
        self.territories.populate(m)

    def on_map_clicked(self, x: float, z: float):
        want_layers = self.inspector.is_active()
        want_objects = self.objects.is_active()
        if not (want_layers or want_objects):
            return
        m = self.current_mission()
        size = m.world_size if m else 0
        if not (0 <= x < size and 0 <= z < size):
            return                               # вне мира: точку не рисуем, старую не трогаем
        af = self.areaflags
        colors = {}
        visible = {r.key: r.btn.isChecked() for r in self.layers_panel._rows}
        if af:
            colors = {f"tier:{n}": self.layer_color(f"tier:{n}") for n in af.values}
            colors |= {f"usage:{n}": self.layer_color(f"usage:{n}") for n in af.usages}
        if want_layers:
            self.inspector.show_at(x, z, af, colors, visible, water=self._water_at(x, z))
        if want_objects:
            self.buildings_feature.show_building_at(x, z, af, colors, visible)


    def on_layer_selected(self, key: str):
        """Выбор слоя (клик по строке / флагу в статистике): в режиме кисти делаем слой
        рисуемым. Авто-показ слоя — в layers_presenter, показ зон — в zones_presenter."""
        if not self.areaflags or key.startswith("obj:"):
            return
        if self.view._brush_mode:
            self.brush_panel.select_layer(key)   # -> on_brush_layer -> подсветка

    # ---------- кисть (правки живут в памяти; запись файла — этап 12) ----------

    def on_brush_mode(self, on: bool):
        """Режим кисти. Слой, по которому рисуем, обязан быть виден — иначе правка
        уходила бы «в невидимое»."""
        if on:
            self.stats_panel.select_switch.setChecked(False)   # два инструмента на ЛКМ — нельзя
        self.view.set_brush_mode(on)
        if on:
            self.view.set_brush_radius(self.brush_panel.radius())
            key = self.brush_panel.layer_key()
            if key:
                self.on_brush_layer(key)
            self.dock_brush.show()
            self.dock_brush.raise_()
        else:
            self.layers_panel.set_active(None)   # вне режима кисти подсветка сбивает

    def on_brush_layer(self, key: str):
        """Активный слой кисти: включаем его показ, строим пиксмап и подсвечиваем строку
        в панели «Слои» — иначе не видно, по чему рисуешь."""
        if not self.areaflags or not key:
            return
        self.layers.auto_show(key)               # покажет слой (временно) и погасит прошлый
        self.layers.ensure_built(key)
        if self.view._brush_mode:
            self.layers_panel.set_active(key)

    def on_brush_erase(self, on: bool):
        self._erase = on

    def on_stroke_started(self):
        self._last_paint = None                  # новый мазок — тянуть не от чего

    def on_paint(self, x: float, z: float):
        """Мазок кисти. Красим ОТРЕЗОК от прошлой точки к текущей: между событиями
        мыши курсор проскакивает десятки метров, и точками выходил пунктир.
        Патчи копятся в _stroke — шагом истории станет весь мазок."""
        af, key = self.areaflags, self.brush_panel.layer_key()
        if not af or not key:
            return
        x0, z0 = self._last_paint or (x, z)      # начало мазка — просто круг
        self._last_paint = (x, z)
        p = stroke(af, key, x0, z0, x, z, self.brush_panel.radius(), erase=self._erase)
        if p is None:
            return                               # вне карты или ничего не изменилось
        self._stroke.append(p)
        self._repaint_patch(key, p.col0, p.row0, p.before.shape)

    def on_shape_committed(self, kind: str, points: list):
        """Enter по контуру: заливка фигуры = один шаг истории, как мазок кисти."""
        af, key = self.areaflags, self.brush_panel.layer_key()
        if not af or not key:
            return
        if kind == "polygon":
            p = fill_polygon(af, key, points, erase=self._erase)
        else:
            (x0, z0), (x1, z1) = points[0], points[1]
            fn = fill_ellipse if kind == "ellipse" else fill_rect
            p = fn(af, key, x0, z0, x1, z1, erase=self._erase)
        if p is None:
            return                               # вырожденный контур или всё уже так
        self.history.push([p])
        self._repaint_patch(key, p.col0, p.row0, p.before.shape)
        self._after_edit()

    def on_stroke_finished(self):
        if not self._stroke:
            return
        self.history.push(self._stroke)
        self._stroke = []
        self._after_edit()

    def on_undo(self):
        step = self.history.undo(self.areaflags)
        if step:
            self._repaint_step(step)
            self._after_edit()

    def on_redo(self):
        step = self.history.redo(self.areaflags)
        if step:
            self._repaint_step(step)
            self._after_edit()

    def _repaint_step(self, step: list):
        """Одна перерисовка на слой, а не на каждый патч: у мазка их десятки, и
        поштучная перерисовка стоила ~6 мс каждая (undo мазка занимал 250 мс).
        Данные откатывает numpy за 0.1 мс — платили только за картинку."""
        boxes: dict[str, list[int]] = {}
        for p in step:
            h, w = p.before.shape
            b = boxes.get(p.key)
            r = [p.col0, p.row0, p.col0 + w, p.row0 + h]
            if b is None:
                boxes[p.key] = r
            else:
                b[0], b[1] = min(b[0], r[0]), min(b[1], r[1])
                b[2], b[3] = max(b[2], r[2]), max(b[3], r[3])
        for key, (c0, r0, c1, r1) in boxes.items():
            self._repaint_patch(key, c0, r0, (r1 - r0, c1 - c0))

    def _repaint_patch(self, key: str, col0: int, row0: int, shape):
        """Перерисовать в оверлее только затронутый кусок (полная пересборка 4096²
        не успевала бы за курсором)."""
        af = self.areaflags
        h, w = shape
        arr, bit = plane_array(af, key)
        sub = arr[row0:row0 + h, col0:col0 + w]
        mask = ((sub >> np.asarray(bit, sub.dtype)) & 1).astype(bool)
        rgba = mask_rgba(mask, self.layer_color(key))
        # пиксмап слоя: север сверху, поэтому верх патча = grid_y - (row0 + h)
        self.view.patch_overlay(key, col0, af.grid_y - (row0 + h), rgba)

    def dirty_cells(self) -> int:
        """Ячеек, отличающихся от файла на диске. Считаем сравнением с исходными
        данными, а не накоплением правок: undo должен возвращать счётчик назад, а
        закрашивание уже закрашенного — не увеличивать его."""
        af, orig = self.areaflags, self._af_orig
        if not af or orig is None:
            return 0
        return int(np.count_nonzero((af.usage != orig[0]) | (af.tier != orig[1])))

    def on_save(self, force: bool = False):
        """Запись areaflags.map: подтверждение → бэкап → атомарная замена → проверка."""
        af = self.areaflags
        if not af or not self._dirty_cells:
            return
        crlf = tr("save.crlf_note", n=af.repaired_crlf) if af.repaired_crlf else ""
        ok = QMessageBox.question(
            self, tr("save.title"),
            tr("save.confirm", n=f"{self._dirty_cells:,}".replace(",", " "),
               path=af.source_path, crlf=crlf),
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel)
        if ok != QMessageBox.StandardButton.Save:
            return
        try:
            info = save_areaflags(af, force=force)
        except FileChangedError:
            again = QMessageBox.warning(
                self, tr("save.title"), tr("save.changed_on_disk"),
                QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if again == QMessageBox.StandardButton.Save:
                self.on_save(force=True)
            return
        except WriteError as e:
            QMessageBox.critical(self, tr("save.title"), tr("save.failed", err=e))
            return
        # файл на диске теперь равен памяти: снимок и счётчик — заново
        self._af_orig = (af.usage.copy(), af.tier.copy())
        self._dirty_cells = 0
        self.brush_panel.set_dirty(0)
        self.lbl_af.setText(tr("af.v1"))
        self.lbl_af.setStyleSheet("")
        self.statusBar().showMessage(
            tr("save.done", bytes=f"{info['bytes']:,}".replace(",", " "),
               backup=os.path.basename(info["backup"]) or "—"), 10000)

    def _after_edit(self):
        """Правка изменила данные: история, счётчик, зоны и статистика устарели."""
        self._dirty_cells = self.dirty_cells()
        self.brush_panel.set_history(*self.history.depth)
        self.brush_panel.set_dirty(self._dirty_cells)
        self.zones.invalidate()                  # зоны считались по старым данным
        self.refresh_stats()

    # ---------- проект CE Tool (импорт TGA-слоёв) ----------

    def choose_ce_project(self):
        folder = QFileDialog.getExistingDirectory(self, tr("dlg.ce_dir"))
        if folder:
            self.load_ce_project(folder)

    def load_ce_project(self, folder: str):
        self.on_ce_clear_overlay()
        try:
            proj = read_project(folder)
        except Exception as e:
            self.ce_project = None
            self.ce_panel.show_error(tr("ce.bad", err=e))
            return
        af = self.areaflags
        if af and proj.layer_size != af.grid_x:
            self.ce_project = None
            self.ce_panel.show_error(
                tr("ce.mismatch", proj=proj.layer_size, live=af.grid_x))
            return
        self.ce_project = proj
        try:
            self.ce_water = water_mask(proj)     # bool-грид или None
        except Exception:
            self.ce_water = None
        names = [l.name for l in proj.layers]
        self.ce_panel.show_project(os.path.basename(proj.path), names,
                                   self.ce_water is not None)
        self.dock_ce.show()
        self.dock_ce.raise_()

    def _water_at(self, x: float, z: float) -> bool | None:
        """Вода/суша в мировой точке из water-fresh проекта (row 0 = ЮГ)."""
        af = self.areaflags
        if self.ce_water is None or af is None:
            return None
        col = int(x / af.cell_size)
        row = int(z / af.cell_size)
        h, w = self.ce_water.shape
        if 0 <= col < w and 0 <= row < h:
            return bool(self.ce_water[row, col])
        return None

    def on_ce_water(self, on: bool):
        """Оверлей воды из проекта (синий, там где water-fresh закрашен)."""
        if not on or self.ce_water is None:
            self.view.set_overlay("ce:water", None)
            return
        rgba = mask_rgba(self.ce_water, (33, 150, 243))
        self.view.set_overlay("ce:water", _rgba_pixmap(rgba), z=25, opacity=0.5)
        self.view.set_overlay_visible("ce:water", True)

    def on_ce_layer(self, name: str):
        """Наложить слой проекта поверх карты для сравнения с боевым areaflags."""
        proj = self.ce_project
        if not proj:
            return
        try:
            mask = layer_mask(proj, name)
        except Exception as e:
            self.ce_panel.show_error(tr("ce.tga_fail", name=name, err=e))
            return
        if self._ce_layer_key:
            self.view.set_overlay(self._ce_layer_key, None)
        layer = proj.layer(name)
        color = layer.color if layer else (255, 235, 59)
        self._ce_layer_key = f"ce:layer:{name}"
        self.view.set_overlay(self._ce_layer_key, _rgba_pixmap(mask_rgba(mask, color)),
                              z=26, opacity=0.6)
        self.view.set_overlay_visible(self._ce_layer_key, True)
        self.ce_panel.set_overlay_active(True)

    def on_ce_clear_overlay(self):
        if self._ce_layer_key:
            self.view.set_overlay(self._ce_layer_key, None)
            self._ce_layer_key = None
        self.ce_panel.set_overlay_active(False)

    # ---------- дифф двух areaflags.map ----------

    def choose_diff_file(self):
        """Второй срез: выбираем ЕГО areaflags.map — порядок битов берём из
        cfglimitsdefinition.xml рядом с ним, а не из текущей карты (они могут не совпасть)."""
        if not self.areaflags:
            return
        p, _ = QFileDialog.getOpenFileName(self, tr("dlg.diff_title"), "",
                                           tr("dlg.diff_filter"))
        if p:
            self.load_diff(p)

    def load_diff(self, path: str, raise_dock: bool = True):
        self.on_diff_clear()
        folder = os.path.dirname(path)
        if not os.path.isfile(os.path.join(folder, "cfglimitsdefinition.xml")):
            self.diff_panel.show_error(tr("diff.no_limits"))
            return
        try:
            self.diff_other = read_areaflags(folder)
            # текущая (правленая) карта = «после», загруженная = «до»:
            # «Появилось» = что ВЫ добавили относительно загруженной
            d = diff_maps(self.diff_other, self.areaflags)
        except DiffError as e:
            self.diff_other = None
            self.diff_panel.show_error(tr("diff.incomparable", err=e))
            return
        except Exception as e:
            self.diff_other = None
            self.diff_panel.show_error(tr("diff.error", err=e))
            return
        self.diff_panel.show_diff(d, os.path.basename(folder) or folder)
        if raise_dock:                           # авто-дифф при загрузке дока не поднимает
            self.dock_diff.show()
            self.dock_diff.raise_()

    def on_diff_flag(self, key: str):
        """Оверлей различий одного флага поверх карты."""
        if not self.diff_other:
            return
        if self._diff_key:
            self.view.set_overlay(f"diff:{self._diff_key}", None)
        # та же ориентация, что и таблица: added = есть у вас, нет в загруженной
        added, removed = diff_planes(self.diff_other, self.areaflags, key)
        self._diff_key = key
        self.view.set_overlay(f"diff:{key}", build_diff_pixmap(added, removed),
                              z=40, opacity=0.9)   # поверх слоёв: дифф важнее заливок

    def on_diff_clear(self):
        if self._diff_key:
            self.view.set_overlay(f"diff:{self._diff_key}", None)
            self._diff_key = None
        self.diff_other = None
        self.diff_panel.clear()

    # ---------- статистика и выделение области ----------

    def on_select_toggled(self, on: bool):
        """Тогл «Выделение области» в панели «Статистика»: ЛКМ тянет рамку вместо пана (пан
        остаётся на ПКМ). Выключение убирает выделение с карты и возвращает охват к всей карте."""
        if on:
            self.brush_panel.sw_mode.setChecked(False)   # ЛКМ занимает кто-то один
        self.view.set_select_mode(on)            # строго ПОСЛЕ выключения кисти
        if not on:
            self.view.clear_region()             # селектор пропадает с карты
        self.refresh_stats(now=True)
        self.refresh_region_loot()

    def on_region_selected(self, x0: float, z0: float, x1: float, z1: float):
        """Нарисовали рамку (тогл включён) — статистика/лут считаются по выделению."""
        self.refresh_stats(now=True)
        self.refresh_region_loot()

    def on_clear_region(self):
        """Выделение снято кликом по карте. Режим рамки НЕ выключаем (тогл остаётся включён):
        пользователь снял прямоугольник, а не вышел из инструмента — охват вернётся к карте."""
        self.view.clear_region()
        self.refresh_stats(now=True)
        if self.buildings is not None:
            self.loot_panel.clear()

    def region_cells(self):
        """Ячейки выделения (col0, row0, col1, row1) или None — если тогл выключен / нет рамки."""
        af, world = self.areaflags, self.view.region()
        if not af or world is None:
            return None
        if not self.stats_panel.select_switch.isChecked():
            return None
        return region_from_world(af, *world)

    def refresh_stats(self, now: bool = False):
        """Планирует пересчёт сводки. Считать её на КАЖДЫЙ мазок кисти нельзя: даже
        ускоренная, она идёт ~100 мс по всей карте — рука это чувствует. Поэтому:
        панель скрыта → не считаем вовсе (пометим устаревшей), иначе коалесцируем серию
        мазков одним таймером. now=True — когда пользователь ждёт ответ сейчас
        (загрузка карты, смена охвата)."""
        if not self.areaflags:
            self._stats_timer.stop()
            self._stats_dirty = False
            self.stats_panel.clear()
            return
        if not self.dock_stats.isVisible():
            self._stats_dirty = True             # пересчитаем, когда панель покажут
            return
        if now:
            self._stats_timer.stop()
            self._do_refresh_stats()
        else:
            self._stats_timer.start()            # рестарт: серия мазков = один пересчёт

    def _on_stats_visible(self, visible: bool):
        if visible and self._stats_dirty:
            self.refresh_stats(now=True)

    def _do_refresh_stats(self):
        af = self.areaflags
        if not af:
            self._stats_dirty = False
            self.stats_panel.clear()
            return
        if not self.dock_stats.isVisible():
            self._stats_dirty = True             # панель закрыли, пока таймер тикал
            return
        self._stats_dirty = False
        region = self.region_cells()
        b = self.buildings
        st = map_stats(af, region,
                       b.x if b is not None else None,
                       b.z if b is not None else None)
        colors = {f.key: self.layer_color(f.key) for f in st.flags}
        self.stats_panel.show_stats(st, colors,
                                    self.view.region() if region else None)

    def refresh_region_loot(self):
        """Сводка спавна по выделению (остаток этапа 6): что может лежать в области."""
        region = self.region_cells()
        b = self.buildings
        if region is None or b is None or self.types is None:
            return
        idx = buildings_in_region(self.areaflags, b, region)
        rows = items_for_region(self.types, b, idx, self.bld_eff_u, self.bld_eff_v)
        self.loot_panel.show_region_items(len(idx), rows)
        self.dock_loot.show()
        self.dock_loot.raise_()

    def on_lang_changed(self, lang: str):
        if lang == self.settings.lang:
            return
        self.settings.lang = lang
        self.settings.save()
        self.language_changed.emit(lang)         # app.py пересоздаст окно



    # ---------- статус ----------

    def on_cursor(self, x: float, z: float):
        self.status_coords.setText(f"X {x:7.1f}   Z {z:7.1f}")
