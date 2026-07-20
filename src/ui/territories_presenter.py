"""Фича «Территории» (круги животных) — паттерн MVP/Passive-View.

Слой на файл `env/*_territories.xml`: круги в мировом радиусе. Владеет панелью и доком,
читает территории для карты, красит/показывает/меняет прозрачность. Цвет по умолчанию —
из файла территории (кладём в общий `territory_colors`, которым пользуется и
`common.layer_colors.LayerColors`).

В лёгком редакторе территории не грузятся (env не материализуется) — там хук
`_load_territories` переопределён в no-op, поэтому `populate` просто не вызывается.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDockWidget

from common.layer_colors import LayerColors
from core.i18n import tr
from core.territories import read_territories
from ui.layers_panel import TerritoriesPanel


class TerritoriesPresenter(QObject):
    """Создать: `TerritoriesPresenter(parent, view=..., colors=..., settings=...,
    mission=..., territory_colors=..., wrap=...)`. Наружу: `.panel`, `.dock`, populate / clear."""

    def __init__(self, parent, *, view, colors: LayerColors, settings, mission: Callable,
                 territory_colors: dict, wrap: Callable):
        super().__init__(parent)
        self.panel = TerritoriesPanel(parent)
        self._view = view
        self._colors = colors
        self._settings = settings
        self._mission = mission
        self._terr_colors = territory_colors          # общий dict (его же читает LayerColors)

        self.panel.layer_toggled.connect(self._on_toggled)
        self.panel.color_clicked.connect(self._on_color_clicked)
        self.panel.opacity_changed.connect(self._on_opacity)

        self.dock = QDockWidget(tr("dock.territories"), parent)
        self.dock.setObjectName("dock_territories")
        self.dock.setWidget(wrap(self.panel))

    def populate(self, mission) -> None:
        """Прочитать территории карты, показать круги и заполнить панель."""
        try:
            layers = read_territories(mission.path)
        except Exception:
            layers = []
        items = []
        for territory in layers:
            key = f"terr:{territory.name}"
            self._terr_colors[key] = territory.color     # дефолт из файла (для сброса цвета)
            color = self._colors.color(key)              # переопределение или дефолт
            self._view.set_territory(key, territory.x, territory.z, territory.r, color)
            items.append((key, territory.name, color, territory.count))
        self.panel.populate(items)
        self._view.set_territory_opacity(self.panel.opacity("terr:"))

    def clear(self) -> None:
        self.panel.clear()
        self._terr_colors.clear()

    def _on_toggled(self, key: str, visible: bool) -> None:
        self._view.set_territory_visible(key, visible)

    def _on_opacity(self, prefix: str, value: int) -> None:
        self._view.set_territory_opacity(value / 100.0)

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
        self._view.set_territory_color(key, rgb)
