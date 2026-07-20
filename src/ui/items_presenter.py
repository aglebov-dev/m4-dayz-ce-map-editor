"""Фича «Предметы» (обратный матчинг) — паттерн MVP/Passive-View.

Панель со списком типов CE и мультивыбором: отмеченные предметы → объединённый слой
зданий, где они могут заспавниться (через `BuildingsModel.instances_for_items`). Владеет
панелью и доком. Прозрачность слоя зданий берём общую с obj-слоями (`building_opacity`).

Зависимости передаются ЯВНО: `buildings` (текущая модель зданий) и `building_opacity`
(общая прозрачность слоя зданий) — как callables, т.к. меняются по ходу работы.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDockWidget

from core.i18n import tr
from ui.items_panel import ItemsPanel

ITEM_LAYER_COLOR = (255, 64, 200)


class ItemsPresenter(QObject):
    """Создать: `ItemsPresenter(parent, view=..., buildings=..., building_opacity=...,
    wrap=...)`. Наружу: `.panel`, `.dock`, populate / clear."""

    def __init__(self, parent, *, view, buildings: Callable, building_opacity: Callable,
                 wrap: Callable):
        super().__init__(parent)
        self.panel = ItemsPanel(parent)
        self._view = view
        self._buildings = buildings
        self._building_opacity = building_opacity
        self.panel.selection_changed.connect(self._on_selection)
        self.dock = QDockWidget(tr("dock.items"), parent)
        self.dock.setObjectName("dock_items")
        self.dock.setWidget(wrap(self.panel))

    def populate(self, types) -> None:
        self.panel.populate(types)

    def clear(self) -> None:
        self.panel.clear()

    def _on_selection(self, names: list[str]) -> None:
        model = self._buildings()
        if not names or model is None or model.types is None:
            self._view.set_buildings("items", None, None, (0, 0, 0))
            self.panel.set_result(0)
            return
        selection = model.instances_for_items(names)
        buildings = model.buildings
        self._view.set_buildings("items", buildings.x[selection], buildings.z[selection],
                                 ITEM_LAYER_COLOR, indices=selection)
        self._view.set_buildings_opacity(self._building_opacity())
        self._view.set_buildings_visible("items", True)
        self.panel.set_result(len(selection))
