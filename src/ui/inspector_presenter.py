"""Фича «Инспектор слоёв» — паттерн MVP/Passive-View.

- Model: `core.areaflags` (данные точки готовит вызывающий и передаёт в `show_at`).
- View:  `InspectorPanel` (пассивная) и `MapView` (маркер точки).
- Здесь: презентер — владеет панелью и доком, показывает попавшие в точку флаги и ставит
  маркер, гасит маркер при выключении, применяет тогл слоя через `AppBus`.

Клик по карте — ОБЩИЙ для инспектора слоёв и инспектора объектов, поэтому его диспетчер
(`MainWindow.on_map_clicked`) остаётся центральным и вызывает `show_at`. Общие данные точки
(цвета/видимость слоёв) считает диспетчер и передаёт сюда явно.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtWidgets import QDockWidget

from core.i18n import tr
from ui.app_bus import AppBus
from ui.inspector_panel import InspectorPanel


class InspectorPresenter(QObject):
    """Создать: `InspectorPresenter(parent, view=..., bus=..., wrap=...)`.
    Наружу: `.panel`, `.dock`, is_active / show_at."""

    def __init__(self, parent, *, view, bus: AppBus, wrap: Callable):
        super().__init__(parent)
        self.panel = InspectorPanel(parent)
        self._view = view

        self.panel.sw_active.toggled.connect(self._on_toggled)
        # тогл слоя из инспектора -> на шину -> применит презентер слоёв (единый источник)
        self.panel.layer_toggle_requested.connect(bus.layer_toggle_requested)
        bus.layer_toggled.connect(self.panel.update_layer_state)

        self.dock = QDockWidget(tr("dock.inspector_layers"), parent)
        self.dock.setObjectName("dock_inspector")
        self.dock.setWidget(wrap(self.panel))

    def is_active(self) -> bool:
        return self.panel.is_active()

    def show_at(self, x: float, z: float, areaflags, colors: dict, visible: dict,
                *, water) -> None:
        """Показать флаги, попавшие в точку, и поставить маркер (точка — только у инспектора слоёв)."""
        self.panel.show_point(x, z, areaflags, colors, visible, water=water)
        self._view.set_marker(x, z)

    def _on_toggled(self, active: bool) -> None:
        if not active:
            self._view.clear_marker()            # точка принадлежит инспектору слоёв
