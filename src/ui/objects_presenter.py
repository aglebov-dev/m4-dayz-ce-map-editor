"""Фича «Объекты» (здания) — паттерн MVP/Passive-View.

Три панели одной подсистемы: obj-слои (здания по эффективным флагам), инспектор
ближайшего здания и спавн (что в нём лежит). Все три вращаются вокруг выбора здания,
поэтому живут в одном презентере. Данные берёт из `common.buildings.BuildingsModel`.

Владеет своими панелями и доками (контракт «фича владеет доком»); MainWindow только
расставляет доки. Клик по карте — ОБЩИЙ с инспектором слоёв, поэтому его диспетчер
(`MainWindow.on_map_clicked`) остаётся центральным и зовёт `show_building_at`.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDockWidget

from common.layer_colors import LayerColors
from core.i18n import tr
from ui.app_bus import AppBus
from ui.layers_panel import ObjectsLayersPanel
from ui.loot_panel import LootPanel
from ui.objects_panel import ObjectsInspectorPanel


class ObjectsPresenter(QObject):
    """Создать: `ObjectsPresenter(parent, view=..., colors=..., settings=..., mission=...,
    bus=..., wrap=...)`. Наружу: панели `.obj_layers/.inspector_panel/.loot_panel`, доки
    `.dock_layers/.dock_inspector/.dock_loot`; populate / clear / is_active / show_building_at."""

    def __init__(self, parent, *, view, colors: LayerColors, settings,
                 mission: Callable, bus: AppBus, wrap: Callable):
        super().__init__(parent)
        self._view = view
        self._colors = colors
        self._settings = settings
        self._mission = mission
        self._af = None
        self._model = None                       # common.buildings.BuildingsModel | None
        self._built: set[str] = set()            # какие оверлеи зданий уже построены

        # --- obj-слои (здания по флагам) ---
        self._bus = bus
        self.obj_layers = ObjectsLayersPanel(parent)
        self.obj_layers.layer_toggled.connect(self._on_toggled)
        self.obj_layers.color_clicked.connect(self._on_color_clicked)
        self.obj_layers.opacity_changed.connect(self._on_opacity)
        # цвета общие с фичей «Здания»: перекрасили там — синхронно тут
        bus.layer_color_changed.connect(self._on_color_synced)
        self.dock_layers = QDockWidget(tr("layers.objects"), parent)
        self.dock_layers.setObjectName("dock_obj_layers")
        self.dock_layers.setWidget(wrap(self.obj_layers))

        # --- инспектор ближайшего здания ---
        self.inspector_panel = ObjectsInspectorPanel(parent)
        self.inspector_panel.sw_active.toggled.connect(self._on_active_toggled)
        # тогл слоя из инспектора объектов -> на шину -> применит презентер слоёв
        self.inspector_panel.layer_toggle_requested.connect(bus.layer_toggle_requested)
        bus.layer_toggled.connect(self.inspector_panel.update_layer_state)
        self.dock_inspector = QDockWidget(tr("dock.inspector_objects"), parent)
        self.dock_inspector.setObjectName("dock_objects")
        self.dock_inspector.setWidget(wrap(self.inspector_panel))

        # --- спавн (что лежит в выбранном здании) ---
        self.loot_panel = LootPanel(parent)
        self.dock_loot = QDockWidget(tr("dock.loot"), parent)
        self.dock_loot.setObjectName("dock_loot")
        self.dock_loot.setWidget(wrap(self.loot_panel))

    # ---------- заполнение / сброс ----------

    def populate(self, areaflags, model) -> None:
        """Перестроить панель obj-слоёв под карту (счётчики из модели, цвета — из common)."""
        self._af = areaflags
        self._model = model
        self._built.clear()
        rows = []
        if model:
            for key, name, count in model.layer_summary(areaflags):
                display = tr("layers.no_flags") if name is None else name
                rows.append((key, display, self._colors.color(key), count))
        self.obj_layers.populate(rows)

    def clear(self) -> None:
        self._af = None
        self._model = None
        self._built.clear()
        self.obj_layers.clear()
        self.inspector_panel.clear()
        self.loot_panel.clear()

    def is_active(self) -> bool:
        return self.inspector_panel.is_active()

    def opacity(self) -> float:
        return self.obj_layers.opacity("obj:")

    # ---------- видимость / построение оверлеев зданий ----------

    def _on_toggled(self, key: str, visible: bool) -> None:
        model = self._model
        if visible and model is not None and key not in self._built:
            xs, zs, selection = model.subset(key, self._af)
            self._view.set_buildings(key, xs, zs, self._colors.color(key), indices=selection)
            self._view.set_buildings_opacity(self.obj_layers.opacity("obj:"))
            self._built.add(key)
        self._view.set_buildings_visible(key, visible)

    def _on_opacity(self, prefix: str, value: int) -> None:
        self._view.set_buildings_opacity(value / 100.0)

    def _on_active_toggled(self, active: bool) -> None:
        if not active:
            self._view.set_selected_building(None)   # подсветка — инспектору объектов

    # ---------- цвет ----------

    def _on_color_clicked(self, key: str) -> None:
        chosen = QColorDialog.getColor(
            QColor(*self._colors.color(key)), self.obj_layers,
            tr("color_dlg.title", name=key.split(":", 1)[1]))
        if chosen.isValid():
            self.apply_color(key, (chosen.red(), chosen.green(), chosen.blue()))

    def apply_color(self, key: str, rgb: tuple[int, int, int]) -> None:
        mission = self._mission()
        if not mission:
            return
        self._settings.set_layer_color(mission.name, key, rgb)
        self._settings.save()
        self.obj_layers.row(key).set_color(rgb)
        self._view.set_buildings_color(key, rgb)
        self._bus.layer_color_changed.emit(key, rgb)   # синхронизировать «Здания»

    def _on_color_synced(self, key: str, rgb: tuple[int, int, int]) -> None:
        """Цвет obj-слоя изменили в панели «Здания» — отразить у себя (без сохранения
        и без повторного эмита, иначе петля)."""
        if not key.startswith("obj:"):
            return
        try:
            self.obj_layers.row(key).set_color(rgb)
        except StopIteration:
            return
        self._view.set_buildings_color(key, rgb)

    # ---------- клик по карте (объектная половина общего диспетчера) ----------

    def show_building_at(self, x: float, z: float, areaflags, colors: dict,
                         visible: dict) -> int | None:
        """Возвращает глобальный индекс выбранного здания (или None) — чтобы фича
        «Здания» подсветила тот же footprint."""
        model = self._model
        if model is None:
            return None
        info = model.nearest(x, z, areaflags)
        index = info["index"] if info else None
        self.inspector_panel.show_building(info, areaflags, colors, visible)
        self._view.set_selected_building(index)
        if info and model.types is not None:
            self.loot_panel.show_items(info["name"], model.items_for(info))
        else:
            self.loot_panel.clear()
        return index
