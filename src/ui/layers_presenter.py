"""Фича «Слои» (tier/usage) целиком в ОДНОМ месте — паттерн MVP/Passive-View.

- Model: `core.areaflags` + `common.layer_colors`/`common.palette`.
- View:  `LayersPanel` (пассивная: сигналы + сеттеры) и `MapView` (оверлеи).
- Здесь: презентер — владеет своей панелью и доком, слушает панель, читает модель,
  командует вьюхой и публикует кросс-фичевые события в `AppBus`. Здесь же «авто-показ»
  выбранного слоя (это поведение слоёв) и применение запросов на тогл от других панелей.

Зависимости передаются ЯВНО (см. `__init__`): презентер не знает про `MainWindow` и
тестируется с фейковыми view/settings/bus. Меняешь поведение слоёв — тебе достаточно
этого файла и пассивной `LayersPanel`.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
from PySide6.QtCore import QObject
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QColorDialog, QDockWidget

from common.layer_colors import LayerColors
from core.areaflags import AreaFlags
from core.i18n import tr
from ui.app_bus import AppBus
from ui.layers_panel import LayersPanel
from ui.overlays import build_flag_pixmap


class LayersPresenter(QObject):
    """Создать: `LayersPresenter(parent, view=..., colors=..., settings=..., mission=...,
    bus=..., wrap=...)`. Наружу: `.panel`, `.dock`, populate / clear / ensure_built /
    auto_show / is_visible / apply_color."""

    def __init__(self, parent, *, view, colors: LayerColors, settings,
                 mission: Callable, bus: AppBus, wrap: Callable):
        super().__init__(parent)
        self.panel = LayersPanel(parent)
        self._view = view
        self._colors = colors
        self._settings = settings
        self._mission = mission
        self._bus = bus
        self._areaflags: AreaFlags | None = None
        self._built: set[str] = set()
        self._auto_shown: str | None = None
        self._suppress_auto = False

        self.dock = QDockWidget(tr("dock.layers"), parent)
        self.dock.setObjectName("dock_layers")
        self.dock.setWidget(wrap(self.panel))

        self.panel.layer_toggled.connect(self._on_toggled)
        self.panel.color_clicked.connect(self._on_color_clicked)
        self.panel.opacity_changed.connect(self._on_opacity)
        self.panel.layer_selected.connect(self._bus.layer_selected)
        self._bus.layer_selected.connect(self.auto_show)
        self._bus.layer_toggle_requested.connect(self._apply_toggle)


    def populate(self, areaflags: AreaFlags, *, tiers_on: bool = True) -> None:
        """Перестроить панель под карту (сам считает счётчики и цвета)."""
        self._areaflags = areaflags
        self._built.clear()
        counts_tier = [int(np.count_nonzero(areaflags.tier & (1 << bit)))
                       for bit in range(len(areaflags.values))]
        counts_usage = [int(np.count_nonzero(areaflags.usage & np.uint32(1 << bit)))
                        for bit in range(len(areaflags.usages))]
        colors = {f"tier:{name}": self._colors.color(f"tier:{name}")
                  for name in areaflags.values}
        colors |= {f"usage:{name}": self._colors.color(f"usage:{name}")
                   for name in areaflags.usages}
        self.panel.populate(areaflags, counts_tier, counts_usage, colors, tiers_on=tiers_on)

    def clear(self) -> None:
        self._areaflags = None
        self._built.clear()
        self._auto_shown = None
        self.panel.clear()

    def ensure_built(self, key: str) -> None:
        """Построить оверлей слоя, если ещё не построен (нужно кисти при активации слоя)."""
        if key not in self._built:
            self._build(key)

    def is_visible(self, key: str) -> bool:
        """Показан ли слой сейчас (для смежных фич, напр. зон)."""
        row = next((r for r in self.panel._rows if r.key == key), None)
        return bool(row and row.btn.isChecked())

    def visible_keys(self) -> list[str]:
        """Ключи всех включённых сейчас слоёв — нужно кисти в режиме «Замена»
        (что именно стереть под мазком)."""
        return [r.key for r in self.panel._rows if r.btn.isChecked()]


    def _on_toggled(self, key: str, visible: bool) -> None:
        if self._areaflags is None:
            return
        if not self._suppress_auto and key == self._auto_shown:
            self._auto_shown = None
        if visible:
            self.ensure_built(key)
        self._view.set_overlay_visible(key, visible)
        self._bus.layer_toggled.emit(key, visible)

    def _apply_toggle(self, key: str, visible: bool) -> None:
        """Запрос сменить видимость слоя (из зон/инспектора) — панель слоёв это истина."""
        row = next((r for r in self.panel._rows if r.key == key), None)
        if row:
            row.btn.setChecked(visible)

    def auto_show(self, key: str) -> None:
        """Показать выбранный слой ВРЕМЕННО: сменили выбор — погасили. Слой, включённый
        пользователем через тогл, не трогаем — это его выбор."""
        if self._areaflags is None or key.startswith("obj:"):
            return
        previous = self._auto_shown
        if previous and previous != key:
            row = next((r for r in self.panel._rows if r.key == previous), None)
            if row and row.btn.isChecked():
                self._suppress_auto = True
                row.btn.setChecked(False)
                self._suppress_auto = False
            self._auto_shown = None
        row = next((r for r in self.panel._rows if r.key == key), None)
        if row and not row.btn.isChecked():
            self._suppress_auto = True
            row.btn.setChecked(True)
            self._suppress_auto = False
            self._auto_shown = key

    def _build(self, key: str) -> None:
        areaflags = self._areaflags
        kind, name = key.split(":", 1)
        bit = (areaflags.values.index(name) if kind == "tier"
               else areaflags.usages.index(name))
        z = (10 + bit) if kind == "tier" else (20 + bit)
        self._view.set_overlay(
            key, build_flag_pixmap(areaflags, name, self._colors.color(key)),
            z=z, opacity=self.panel.opacity(key))
        self._built.add(key)

    def _on_opacity(self, prefix: str, value: int) -> None:
        self._view.set_overlay_opacity(value / 100.0, prefix=prefix)


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
        if key in self._built:
            self._build(key)
        self._bus.layer_color_changed.emit(key, rgb)
