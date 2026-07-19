"""Фича «Здания» — контуры (footprint) построек на карте, MVP/Passive-View.

Тот же набор слоёв и те же цвета, что у «Объектов» (маркеры совпадают: общий
`obj:`-ключ и общий `LayerColors`), но на карте — залитые прямоугольники footprint из
датасета ресерча (`core.building_index`), а не точки; и своя прозрачность.

Показываем ровно те же здания, что «Объекты» (`common.buildings.BuildingsModel` —
из загруженного mapgroupproto/mapgrouppos): footprint матчится по имени класса, поворот —
по позиции; здания без класса в датасете просто без контура.
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDockWidget

from common.footprints import oriented_corners
from common.layer_colors import LayerColors
from core.i18n import tr
from ui.app_bus import AppBus
from ui.layers_panel import BuildingsLayersPanel


class BuildingsPresenter(QObject):
    """Создать: `BuildingsPresenter(parent, view=..., colors=..., settings=...,
    mission=..., bus=..., wrap=...)`. Наружу: панель `.panel`, док `.dock`;
    populate(af, model, index) / clear / select_building."""

    def __init__(self, parent, *, view, colors: LayerColors, settings,
                 mission: Callable, bus: AppBus, wrap: Callable):
        super().__init__(parent)
        self._view = view
        self._colors = colors
        self._settings = settings
        self._mission = mission
        self._bus = bus
        self._af = None
        self._model = None                       # common.buildings.BuildingsModel | None
        self._index = None                       # core.building_index.BuildingIndex | None
        self._built: set[str] = set()            # какие слои контуров уже построены

        self.panel = BuildingsLayersPanel(parent)
        self.panel.layer_toggled.connect(self._on_toggled)
        self.panel.color_clicked.connect(self._on_color_clicked)
        self.panel.opacity_changed.connect(self._on_opacity)
        # цвета общие с «Объектами»: перекрасили там — синхронно тут (и наоборот)
        bus.layer_color_changed.connect(self._on_color_synced)
        self.dock = QDockWidget(tr("layers.buildings"), parent)
        self.dock.setObjectName("dock_buildings")
        self.dock.setWidget(wrap(self.panel))

    # ---------- заполнение / сброс ----------

    def populate(self, areaflags, model, index) -> None:
        """Слои контуров под карту: те же строки, что «Объекты»; footprint — из index.
        index=None (нет датасета для мира) — панель пустая."""
        self._af = areaflags
        self._model = model
        self._index = index
        self._built.clear()
        rows = []
        if model and index:
            for key, name, count in model.layer_summary(areaflags):
                display = tr("layers.no_flags") if name is None else name
                rows.append((key, display, self._colors.color(key), count))
        self.panel.populate(rows)

    def clear(self) -> None:
        self._af = None
        self._model = None
        self._index = None
        self._built.clear()
        self.panel.clear()

    def opacity(self) -> float:
        return self.panel.opacity("obj:")

    # ---------- видимость / построение контуров ----------

    def _on_toggled(self, key: str, visible: bool) -> None:
        model, index = self._model, self._index
        if visible and model is not None and index is not None and key not in self._built:
            xs, zs, selection = model.subset(key, self._af)
            names = [model.buildings.names[i] for i in selection]
            corners, kept = oriented_corners(xs, zs, names, index)
            self._view.set_footprints(key, corners, self._colors.color(key),
                                      indices=selection[kept])
            self._view.set_footprints_opacity(self.panel.opacity("obj:"))
            self._built.add(key)
        self._view.set_footprints_visible(key, visible)

    def _on_opacity(self, _prefix: str, value: int) -> None:
        self._view.set_footprints_opacity(value / 100.0)

    def select_building(self, index: int | None) -> None:
        """Подсветить выбранное здание (общий клик по карте — из главного окна)."""
        self._view.set_selected_footprint(index)

    # ---------- цвет (общий с «Объектами») ----------

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
        self._view.set_footprints_color(key, rgb)
        self._bus.layer_color_changed.emit(key, rgb)   # синхронизировать «Объекты»

    def _on_color_synced(self, key: str, rgb: tuple[int, int, int]) -> None:
        """Цвет obj-слоя изменили в другой панели («Объекты») — отразить у себя.
        Только UI/карта: без сохранения и без повторного эмита (иначе петля)."""
        if not key.startswith("obj:"):
            return
        try:
            self.panel.row(key).set_color(rgb)
        except StopIteration:
            return                               # этого слоя нет в текущем наборе
        self._view.set_footprints_color(key, rgb)
