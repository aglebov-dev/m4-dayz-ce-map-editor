"""Иконка приложения — рисуется КОДОМ (без загрузки файла с диска).

Простая графика «карта редактора»: скруглённая плитка с сеткой и меткой-пином. Не зависит
от ассетов, темы и шрифтов; отдаётся в нескольких размерах для чёткости в заголовке/таскбаре.
Использовать: `app.setWindowIcon(make_app_icon())`."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QPolygonF,
)

# Палитра иконки (фиксированная — иконка одинакова в любой теме).
_TILE_TOP = QColor("#2f9e8f")        # бирюза-верх
_TILE_BOTTOM = QColor("#184f49")     # тёмный низ
_GRID = QColor(255, 255, 255, 55)    # линии сетки
_PIN = QColor("#ffb300")             # янтарный пин
_PIN_DOT = QColor("#184f49")         # тёмная точка в пине
_EDGE = QColor(0, 0, 0, 45)          # мягкий контур плитки


def _draw(size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    inset = size * 0.09
    tile = QRectF(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = size * 0.17

    gradient = QLinearGradient(tile.topLeft(), tile.bottomRight())
    gradient.setColorAt(0.0, _TILE_TOP)
    gradient.setColorAt(1.0, _TILE_BOTTOM)
    painter.setBrush(gradient)
    painter.setPen(QPen(_EDGE, max(1.0, size * 0.02)))
    painter.drawRoundedRect(tile, radius, radius)

    # сетка карты — тонкие линии (на мелких размерах почти сливаются, это нормально)
    painter.setPen(QPen(_GRID, max(1.0, size * 0.012)))
    for i in (1, 2, 3):
        x = tile.left() + tile.width() * i / 4
        painter.drawLine(QPointF(x, tile.top() + size * 0.05),
                         QPointF(x, tile.bottom() - size * 0.05))
        y = tile.top() + tile.height() * i / 4
        painter.drawLine(QPointF(tile.left() + size * 0.05, y),
                         QPointF(tile.right() - size * 0.05, y))

    # метка-пин (капля + точка) чуть выше центра
    cx, cy, r = size * 0.5, size * 0.44, size * 0.15
    pin = QPainterPath()
    pin.addEllipse(QPointF(cx, cy), r, r)
    pin.addPolygon(QPolygonF([
        QPointF(cx - r * 0.72, cy + r * 0.45),
        QPointF(cx + r * 0.72, cy + r * 0.45),
        QPointF(cx, cy + r * 1.95),
    ]))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(_PIN)
    painter.drawPath(pin.simplified())
    painter.setBrush(_PIN_DOT)
    painter.drawEllipse(QPointF(cx, cy), r * 0.42, r * 0.42)

    painter.end()
    return pixmap


def make_app_icon() -> QIcon:
    """QIcon приложения в наборе размеров (для чёткости в заголовке и панели задач)."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        icon.addPixmap(_draw(size))
    return icon
