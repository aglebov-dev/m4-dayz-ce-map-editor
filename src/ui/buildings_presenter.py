"""Фича «Здания» — MVP/Passive-View. Единственная фича по зданиям (бывшие «Объекты»
слились сюда): слои по флагам + инспектор здания + спавн.

Отображение зданий — в одном из режимов (переключатель в панели): точки / контур / оба.
Точки — маркеры (`map_view.set_buildings`), контур — footprint из датасета
(`common.footprints`, габариты) с yaw из mapgrouppos. Клик по карте выбирает здание: в
режиме с контуром — то, в чей footprint попал клик (иначе ближайшее); в режиме точек —
ближайшее. Если в точке несколько зданий (высотки/наложение) — список в инспекторе.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDockWidget

from common.footprints import footprints_containing, oriented_corners
from common.layer_colors import LayerColors
from core.i18n import tr
from ui.app_bus import AppBus
from ui.layers_panel import BuildingsLayersPanel
from ui.loot_panel import LootPanel
from ui.objects_panel import BuildingInspectorPanel

STACK_RADIUS_M = 2.0


class BuildingsPresenter(QObject):
    """Наружу: панели `.panel/.inspector_panel/.loot_panel`, доки `.dock/.dock_inspector/
    .dock_loot`; populate / clear / is_active / opacity / show_building_at."""

    def __init__(self, parent, *, view, colors: LayerColors, settings,
                 mission: Callable, bus: AppBus, wrap: Callable):
        super().__init__(parent)
        self._view = view
        self._colors = colors
        self._settings = settings
        self._mission = mission
        self._bus = bus
        self._af = None
        self._model = None
        self._index = None
        self._corners = None
        self._kept = None
        self._corner_row: dict[int, int] = {}
        self._built: set[str] = set()
        self._layer_on: dict[str, bool] = {}
        self._cands: dict[int, dict] = {}

        self.panel = BuildingsLayersPanel(parent)
        self.panel.layer_toggled.connect(self._on_toggled)
        self.panel.color_clicked.connect(self._on_color_clicked)
        self.panel.opacity_changed.connect(self._on_opacity)
        self.panel.mode_changed.connect(self._on_mode_changed)
        self.dock = QDockWidget(tr("layers.buildings"), parent)
        self.dock.setObjectName("dock_buildings")
        self.dock.setWidget(wrap(self.panel))

        self.inspector_panel = BuildingInspectorPanel(parent)
        self.inspector_panel.sw_active.toggled.connect(self._on_active_toggled)
        self.inspector_panel.layer_toggle_requested.connect(bus.layer_toggle_requested)
        self.inspector_panel.building_picked.connect(self._on_building_picked)
        bus.layer_toggled.connect(self.inspector_panel.update_layer_state)
        self.dock_inspector = QDockWidget(tr("dock.inspector_objects"), parent)
        self.dock_inspector.setObjectName("dock_objects")
        self.dock_inspector.setWidget(wrap(self.inspector_panel))

        self.loot_panel = LootPanel(parent)
        self.dock_loot = QDockWidget(tr("dock.loot"), parent)
        self.dock_loot.setObjectName("dock_loot")
        self.dock_loot.setWidget(wrap(self.loot_panel))


    def populate(self, areaflags, model, index) -> None:
        self._af = areaflags
        self._model = model
        self._index = index
        self._built.clear()
        self._layer_on.clear()
        self._corners, self._kept, self._corner_row = None, None, {}
        rows = []
        if model and index:
            corners, kept = oriented_corners(model.buildings.x, model.buildings.z,
                                             model.buildings.names, model.buildings.yaw, index)
            self._corners, self._kept = corners, kept
            self._corner_row = {int(g): i for i, g in enumerate(kept)}
            for key, name, count in model.layer_summary(areaflags):
                display = tr("layers.no_flags") if name is None else name
                rows.append((key, display, self._colors.color(key), count))
        self.panel.populate(rows)

    def clear(self) -> None:
        self._af = self._model = self._index = None
        self._corners = self._kept = None
        self._corner_row = {}
        self._built.clear()
        self._layer_on.clear()
        self._cands = {}
        self.panel.clear()
        self.inspector_panel.clear()
        self.loot_panel.clear()

    def is_active(self) -> bool:
        return self.inspector_panel.is_active()

    def opacity(self) -> float:
        """Прозрачность точек (для фичи «Предметы», рисующей здания точками)."""
        return self.panel.points_opacity()


    def _on_toggled(self, key: str, visible: bool) -> None:
        model = self._model
        if model is not None and key not in self._built:
            xs, zs, selection = model.subset(key, self._af)
            color = self._colors.color(key)
            self._view.set_buildings(key, xs, zs, color, indices=selection)
            self._view.set_buildings_opacity(self.panel.points_opacity())
            rows = [self._corner_row[g] for g in selection if g in self._corner_row]
            fp_ids = np.array([g for g in selection if g in self._corner_row], dtype=np.int64)
            corners = self._corners[rows] if rows else np.empty((0, 4, 2))
            self._view.set_footprints(key, corners, color, indices=fp_ids)
            self._view.set_footprints_opacity(self.panel.opacity("obj:"))
            self._view.set_footprints_border_opacity(self.panel.border_opacity())
            self._built.add(key)
        self._layer_on[key] = visible
        self._apply_visibility(key)

    def _apply_visibility(self, key: str) -> None:
        on = self._layer_on.get(key, False)
        mode = self.panel.mode()
        self._view.set_buildings_visible(key, on and mode in ("points", "both"))
        self._view.set_footprints_visible(key, on and mode in ("contour", "both"))

    def _on_mode_changed(self, _mode: str) -> None:
        for key in self._layer_on:
            self._apply_visibility(key)

    def _on_opacity(self, prefix: str, value: int) -> None:
        if prefix == "objpoints:":
            self._view.set_buildings_opacity(value / 100.0)
        elif prefix == "objborder:":
            self._view.set_footprints_border_opacity(value / 100.0)
        else:
            self._view.set_footprints_opacity(value / 100.0)

    def _on_active_toggled(self, active: bool) -> None:
        if not active:
            self._view.set_selected_building(None)
            self._view.set_selected_footprint(None)


    def _on_color_clicked(self, key: str) -> None:
        chosen = QColorDialog.getColor(
            QColor(*self._colors.color(key)), self.panel,
            tr("color_dlg.title", name=key.split(":", 1)[1]))
        if chosen.isValid():
            self.apply_color(key, (chosen.red(), chosen.green(), chosen.blue()))

    def apply_color(self, key: str, rgb: tuple[int, int, int]) -> None:
        mission = self._mission()
        if not mission:
            return
        self._settings.set_layer_color(mission.name, key, rgb)
        self._settings.save()
        self.panel.row(key).set_color(rgb)
        self._view.set_buildings_color(key, rgb)
        self._view.set_footprints_color(key, rgb)
        self._bus.layer_color_changed.emit(key, rgb)


    def show_building_at(self, x: float, z: float, areaflags, colors: dict,
                         visible: dict) -> None:
        """Выбрать здание(я) в точке клика по правилам режима и показать в инспекторе."""
        model = self._model
        if model is None:
            return
        candidates = self._pick(x, z)
        cands = [model.info_at_index(i, areaflags, from_xz=(x, z)) for i in candidates]
        cands.sort(key=lambda c: c["dist"])
        self._cands = {c["index"]: c for c in cands}
        self.inspector_panel.show_buildings(cands, areaflags, colors, visible)
        if not cands:
            self._on_building_picked(None)

    def _pick(self, x: float, z: float) -> list[int]:
        """Глобальные индексы зданий-кандидатов в точке (по режиму отображения)."""
        model, mode = self._model, self.panel.mode()
        if mode in ("contour", "both") and self._corners is not None and len(self._kept):
            rows = footprints_containing(self._corners, x, z)
            if len(rows):
                return [int(g) for g in self._kept[rows]]
        near = model.nearest(x, z, self._af)
        if near is None:
            return []
        stack = model.indices_near(near["x"], near["z"], STACK_RADIUS_M)
        return [int(i) for i in stack] if len(stack) else [near["index"]]

    def _on_building_picked(self, index: int | None) -> None:
        """Здание выбрано (первое из списка или переключение в списке): подсветка + спавн."""
        self._view.set_selected_building(index)
        self._view.set_selected_footprint(index)
        model, info = self._model, (self._cands.get(index) if index is not None else None)
        if info and model is not None and model.types is not None:
            self.loot_panel.show_items(info["name"], model.items_for(info))
        else:
            self.loot_panel.clear()
