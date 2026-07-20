"""Тонкая шина событий между фичами UI.

Зачем: чтобы фичи не соединялись напрямую «панель-в-панель» через god-окно. Источник
события эмитит сигнал шины, потребители подписываются. Где искать обработчик конкретной
фичи — смотри по комментариям рядом с `bus.*.connect(...)` в `ui/main_window.py`.

Сигналы добавляются по мере переноса фич на пресентеры."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppBus(QObject):
    layer_toggled = Signal(str, bool)
    layer_selected = Signal(str)
    layer_color_changed = Signal(str, tuple)
    layer_toggle_requested = Signal(str, bool)
