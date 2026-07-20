"""Фича «Зоны» целиком в ОДНОМ месте — паттерн MVP/Passive-View.

- Model: связные зоны битплана слоя (`core.zones.find_zones`) + цвет из `common`.
- View:  `ZonesPanel` (пассивная) и `MapView` (переход к зоне, подписи зон).
- Здесь: презентер — владеет панелью и доком, кэширует зоны на слой, показывает их при
  выборе слоя (через `AppBus`), пересчитывает после правок кистью, перекрашивает подписи.

Зависимости передаются ЯВНО. Про видимость слоя спрашиваем `is_layer_visible` (её знает
презентер слоёв) — так зоны не лезут в панель слоёв напрямую.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDockWidget

from common.layer_colors import LayerColors
from core.i18n import tr
from core.zones import find_zones
from ui.diag import trace
from ui.app_bus import AppBus
from ui.zones_panel import ZonesPanel


class ZonesPresenter(QObject):
    """Создать: `ZonesPresenter(parent, view=..., colors=..., bus=..., areaflags=...,
    is_layer_visible=..., wrap=...)`. Наружу: `.panel`, `.dock`, clear / invalidate / cached."""

    def __init__(self, parent, *, view, colors: LayerColors, bus: AppBus,
                 areaflags: Callable, is_layer_visible: Callable, wrap: Callable):
        super().__init__(parent)
        self.panel = ZonesPanel(parent)
        self._view = view
        self._colors = colors
        self._areaflags = areaflags
        self._is_visible = is_layer_visible
        self._cache: dict[str, list] = {}
        self._key: str | None = None

        self.panel.zone_clicked.connect(view.zoom_to_world)
        self.panel.zone_selected.connect(view.set_selected_zone)
        self.panel.labels_toggled.connect(view.set_zone_labels_visible)
        self.panel.layer_toggle_requested.connect(bus.layer_toggle_requested)
        bus.layer_toggled.connect(self.panel.update_layer_state)
        bus.layer_selected.connect(self._on_layer_selected)
        bus.layer_color_changed.connect(self._on_color_changed)

        self.dock = QDockWidget(tr("dock.zones"), parent)
        self.dock.setObjectName("dock_zones")
        self.dock.setWidget(wrap(self.panel))
        self.dock.visibilityChanged.connect(self._on_visible)


    def clear(self) -> None:
        """Смена карты: сбросить всё."""
        self._cache.clear()
        self._key = None
        self.panel.clear()
        self._view.set_zone_labels(None, 0.0, (0, 0, 0))

    def invalidate(self) -> None:
        """Правка кистью: зоны считались по старым данным — пересчитать заново при показе."""
        self._cache.clear()
        self.panel.clear()
        self._view.set_zone_labels(None, 0.0, (0, 0, 0))

    def cached(self, key: str) -> list:
        """Зоны слоя из кэша (для экспорта CSV). Пусто, если ещё не считались."""
        return self._cache.get(key) or []


    def _on_layer_selected(self, key: str) -> None:
        areaflags = self._areaflags()
        if not areaflags or key.startswith("obj:"):
            return
        self._key = key
        if self.dock.isVisible():
            self._show(key)

    @trace
    def _on_visible(self, visible: bool) -> None:
        if visible and self._key:
            self._show(self._key)

    def _show(self, key: str) -> None:
        areaflags = self._areaflags()
        if not areaflags:
            return
        zones = self._cache.get(key)
        if zones is None:
            name = key.split(":", 1)[1]
            zones = find_zones(areaflags.plane(name), min_cells=2)
            self._cache[key] = zones
        color = self._colors.color(key)
        self.panel.show_zones(key, key.split(":", 1)[1], zones, areaflags.cell_size,
                              color, self._is_visible(key))
        self._view.set_zone_labels(zones, areaflags.cell_size, color)

    def _on_color_changed(self, key: str, rgb: tuple[int, int, int]) -> None:
        if key == self.panel.layer_key:
            self._view.set_zone_labels_color(rgb)
