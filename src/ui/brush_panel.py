"""Панель «Кисть»: инструмент, размер, кисть/ластик, undo/redo и СВОЙ список слоёв для
выбора слоя рисования (видимостью слоёв по-прежнему рулит панель «Слои»). Клик по
инструменту сразу включает режим рисования; в нём Пробел заливает контур, Tab — кисть/ластик."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider,
    QStyle, QToolButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from ui.layers_panel import Switch


def _tool_icon(kind: str, ink: QColor) -> QIcon:
    """Иконка инструмента, нарисованная кодом: не зависит от шрифта и темы."""
    pm = QPixmap(18, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(ink, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "brush":
        p.setBrush(ink)
        p.drawEllipse(QRectF(5, 5, 8, 8))
    elif kind == "rect":
        p.drawRect(QRectF(3, 4, 12, 10))
    elif kind == "ellipse":
        p.drawEllipse(QRectF(3, 4, 12, 10))
    elif kind == "polygon":
        p.drawPolygon(QPolygonF([QPointF(9, 3), QPointF(15, 8), QPointF(12, 15),
                                 QPointF(6, 15), QPointF(3, 8)]))
    else:
        path = QPainterPath(QPointF(4, 14))
        path.cubicTo(QPointF(0, 4), QPointF(18, 2), QPointF(12, 10))
        path.cubicTo(QPointF(8, 15), QPointF(5, 9), QPointF(9, 8))
        p.drawPath(path)
    p.end()
    return QIcon(pm)


class BrushLayerRow(QWidget):
    """Строка слоя-выбора кисти: квадратик цвета + имя, без свитча и «×». Клик — выбрать."""

    def __init__(self, key: str, name: str, color: tuple[int, int, int],
                 list_widget: "BrushLayerList"):
        super().__init__(list_widget)
        self.key = key
        self._list = list_widget
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.swatch = QLabel(self)
        self._set_swatch(color)
        self.text = QLabel(name, self)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 1, 2, 1)
        lay.addWidget(self.swatch)
        lay.addWidget(self.text, 1)

    def mousePressEvent(self, ev):
        self._list.layer_selected.emit(self.key)
        super().mousePressEvent(ev)

    def set_active(self, on: bool):
        self.setStyleSheet(
            "background: rgba(33, 150, 243, 70); border-radius: 3px;" if on else "")
        f = self.text.font()
        f.setBold(on)
        self.text.setFont(f)

    def set_color(self, rgb: tuple[int, int, int]):
        self._set_swatch(rgb)

    def _set_swatch(self, rgb):
        pm = QPixmap(14, 14)
        pm.fill(QColor(*rgb))
        self.swatch.setPixmap(pm)


class BrushLayerList(QWidget):
    """Список слоёв (тиры/usage) для выбора слоя рисования: заголовки разделов + строки
    без переключателей. Видимость слоёв не трогает — только выбор активного слоя кисти."""

    layer_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[BrushLayerRow] = []
        self._active: str | None = None
        self.layer_selected.connect(self.set_active)
        self._list_lay = QVBoxLayout()
        self._list_lay.setSpacing(0)
        inner = QWidget()
        inner.setLayout(self._list_lay)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(inner)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(scroll)

    def populate(self, sections: list[tuple[str, list[tuple[str, str, tuple[int, int, int]]]]]):
        """sections — [(заголовок, [(key, имя, цвет), …]), …]."""
        self.clear()
        for title, rows in sections:
            if not rows:
                continue
            head = QLabel(f"<b>{title}</b>")
            head.setContentsMargins(2, 6, 2, 2)
            self._list_lay.addWidget(head)
            for key, name, color in rows:
                row = BrushLayerRow(key, name, color, self)
                self._rows.append(row)
                self._list_lay.addWidget(row)
        self._list_lay.addStretch(1)
        if self._active:
            self.set_active(self._active)

    def clear(self):
        self._rows.clear()
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def keys(self) -> list[str]:
        return [r.key for r in self._rows]

    def active_key(self) -> str | None:
        return self._active

    def set_active(self, key: str | None):
        self._active = key
        for r in self._rows:
            r.set_active(r.key == key)

    def set_color(self, key: str, rgb: tuple[int, int, int]):
        for r in self._rows:
            if r.key == key:
                r.set_color(rgb)


class BrushPanel(QWidget):
    """Сигналы: mode_toggled(on), tool_changed(kind), apply_shape(), cancel_shape(),
    layer_changed(key), radius_changed(m), erase_toggled(on), replace_toggled(on),
    undo/redo_requested()."""

    mode_toggled = Signal(bool)
    tool_changed = Signal(str)
    apply_shape = Signal()
    cancel_shape = Signal()
    layer_changed = Signal(str)
    radius_changed = Signal(float)
    erase_toggled = Signal(bool)
    replace_toggled = Signal(bool)
    undo_requested = Signal()
    redo_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sw_mode = Switch((33, 150, 243), self)
        self.sw_mode.setToolTip(tr("brush.mode_tip"))
        self.sw_mode.toggled.connect(self.mode_toggled)
        head = QHBoxLayout()
        head.addWidget(self.sw_mode)
        head.addWidget(QLabel(tr("brush.mode")), 1)

        self.tools = QButtonGroup(self)
        self.tools.setExclusive(True)
        t_row = QHBoxLayout()
        t_row.setSpacing(2)
        for name, tip in (("brush", "brush.tool_brush"), ("rect", "brush.tool_rect"),
                          ("ellipse", "brush.tool_ellipse"),
                          ("polygon", "brush.tool_polygon"),
                          ("lasso", "brush.tool_lasso")):
            b = QToolButton()
            ink = b.palette().color(QPalette.ColorRole.ButtonText)
            b.setIcon(_tool_icon(name, ink))
            b.setToolTip(tr(tip))
            b.setCheckable(True)
            b.setChecked(name == "brush")
            b.setProperty("tool", name)
            self.tools.addButton(b)
            t_row.addWidget(b)
        t_row.addStretch(1)
        self.tools.buttonClicked.connect(self._on_tool)

        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setRange(5, 500)
        self.sld.setValue(50)
        self.sld.valueChanged.connect(self._on_radius)
        self.lbl_radius = QLabel()
        self.lbl_radius.setMinimumWidth(64)
        r_row = QHBoxLayout()
        r_row.addWidget(QLabel(tr("brush.size")))
        r_row.addWidget(self.sld, 1)
        r_row.addWidget(self.lbl_radius)

        self.sw_erase = Switch((244, 67, 54), self)
        self.sw_erase.setToolTip(tr("brush.erase_tip"))
        self.sw_erase.toggled.connect(self._on_erase)
        self.sw_replace = Switch((255, 152, 0), self)
        self.sw_replace.setToolTip(tr("brush.replace_tip"))
        self.sw_replace.toggled.connect(self._on_replace)
        e_row = QHBoxLayout()
        e_row.addWidget(self.sw_erase)
        e_row.addWidget(QLabel(tr("brush.erase")))
        e_row.addSpacing(12)
        e_row.addWidget(self.sw_replace)
        e_row.addWidget(QLabel(tr("brush.replace")), 1)

        st = self.style()
        self.btn_undo = QPushButton(
            st.standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "")
        self.btn_undo.setToolTip(f'{tr("brush.undo")} (Ctrl+Z)')
        self.btn_undo.clicked.connect(self.undo_requested)
        self.btn_undo.setEnabled(False)
        self.btn_redo = QPushButton(
            st.standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "")
        self.btn_redo.setToolTip(f'{tr("brush.redo")} (Ctrl+Y)')
        self.btn_redo.clicked.connect(self.redo_requested)
        self.btn_redo.setEnabled(False)
        u_row = QHBoxLayout()
        u_row.addWidget(self.btn_undo)
        u_row.addWidget(self.btn_redo)
        u_row.addStretch(1)

        self.btn_apply = QPushButton(tr("brush.apply"))
        self.btn_apply.setToolTip(tr("brush.apply_tip"))
        self.btn_apply.clicked.connect(self.apply_shape)
        self.btn_cancel = QPushButton(tr("brush.cancel"))
        self.btn_cancel.clicked.connect(self.cancel_shape)
        s_row = QHBoxLayout()
        s_row.addWidget(self.btn_apply)
        s_row.addWidget(self.btn_cancel)
        self.set_shape_ready(False)

        self.lbl_state = QLabel(tr("brush.saved"))
        self.lbl_state.setWordWrap(True)
        self.lbl_state.setTextFormat(Qt.TextFormat.RichText)

        self.lbl_pick = QLabel(tr("brush.pick_layer"))
        self.layer_list = BrushLayerList(self)
        self.layer_list.layer_selected.connect(self.layer_changed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addLayout(t_row)
        lay.addLayout(r_row)
        lay.addLayout(e_row)
        lay.addLayout(s_row)
        lay.addLayout(u_row)
        lay.addWidget(self.lbl_state)
        lay.addWidget(self.lbl_pick)
        lay.addWidget(self.layer_list, 1)
        self._on_radius(self.sld.value())


    def populate(self, tiers: list[tuple[str, str, tuple[int, int, int]]],
                 usages: list[tuple[str, str, tuple[int, int, int]]]):
        """tiers/usages — [(key, имя, цвет)]. Первый слой становится активным."""
        self.layer_list.populate([(tr("layers.tiers"), tiers),
                                  (tr("layers.usage"), usages)])
        keys = self.layer_list.keys()
        if keys:
            self.layer_list.set_active(keys[0])
            self.layer_changed.emit(keys[0])

    def clear(self):
        self.layer_list.clear()
        self.sw_mode.setChecked(False)
        self.sw_erase.setChecked(False)
        self.sw_replace.setChecked(False)
        self.set_history(0, 0)
        self.set_dirty(0)

    def layer_key(self) -> str | None:
        return self.layer_list.active_key()

    def select_layer(self, key: str):
        if key != self.layer_list.active_key():
            self.layer_list.set_active(key)

    def set_layer_color(self, key: str, rgb: tuple[int, int, int]):
        self.layer_list.set_color(key, rgb)

    def radius(self) -> float:
        return float(self.sld.value())

    def set_shape_ready(self, ready: bool):
        self.btn_apply.setEnabled(ready)
        self.btn_cancel.setEnabled(ready)

    def tool(self) -> str:
        b = self.tools.checkedButton()
        return b.property("tool") if b else "brush"

    def set_history(self, undo: int, redo: int):
        self.btn_undo.setEnabled(undo > 0)
        self.btn_redo.setEnabled(redo > 0)

    def set_dirty(self, cells: int):
        """Сколько ячеек отличается от файла на диске (0 — правок нет). Кнопка сохранения
        живёт в верхнем тулбаре, тут — только счётчик."""
        if cells:
            self.lbl_state.setText(tr("brush.dirty", n=f"{cells:,}".replace(",", " ")))
        else:
            self.lbl_state.setText(tr("brush.saved"))

    def _on_erase(self, on: bool):
        if on and self.sw_replace.isChecked():
            self.sw_replace.setChecked(False)
        self.erase_toggled.emit(on)

    def _on_replace(self, on: bool):
        if on and self.sw_erase.isChecked():
            self.sw_erase.setChecked(False)
        self.replace_toggled.emit(on)

    def _on_tool(self, b):
        """Клик по инструменту: выбрать его и сразу включить режим рисования."""
        self.tool_changed.emit(b.property("tool"))
        if not self.sw_mode.isChecked():
            self.sw_mode.setChecked(True)

    def _on_radius(self, v: int):
        self.lbl_radius.setText(tr("brush.radius_m", m=v))
        self.radius_changed.emit(float(v))
