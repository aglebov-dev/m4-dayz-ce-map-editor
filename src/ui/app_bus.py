"""Тонкая шина событий между фичами UI.

Зачем: чтобы фичи не соединялись напрямую «панель-в-панель» через god-окно. Источник
события эмитит сигнал шины, потребители подписываются. Где искать обработчик конкретной
фичи — смотри по комментариям рядом с `bus.*.connect(...)` в `ui/main_window.py`.

Сигналы добавляются по мере переноса фич на пресентеры."""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AppBus(QObject):
    # видимость слоя изменилась. Источник: LayersPresenter.        (key, visible)
    layer_toggled = Signal(str, bool)
    # слой выбран — показать его зоны/подписи. Источники: строка панели слоёв, клик в статистике.
    layer_selected = Signal(str)
    # цвет слоя изменён. Источник: LayersPresenter.                (key, rgb)
    layer_color_changed = Signal(str, tuple)
    # запрос сменить видимость слоя из другой панели (зоны/инспектор). Применяет
    # LayersPresenter (панель слоёв — единый источник истины).            (key, visible)
    layer_toggle_requested = Signal(str, bool)
