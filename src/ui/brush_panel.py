"""Панель «Кисть»: активный слой, размер, кисть/ластик, undo/redo.
Правки живут в памяти — запись areaflags.map на диск будет этапом 12."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import (
    QColor, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap, QPolygonF,
)
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QPushButton, QSlider, QStyle,
    QToolButton, QVBoxLayout, QWidget,
)

from core.i18n import tr
from ui.layers_panel import Switch


def _tool_icon(kind: str, ink: QColor) -> QIcon:
    """Иконка инструмента, нарисованная кодом: не зависит от шрифта и темы.
    Цвет — из палитры кнопки (ButtonText): светлый на тёмной теме, тёмный на светлой,
    контраст подбирает тема. QToolButton гасит иконку при выключении сам."""
    pm = QPixmap(18, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(ink, 1.6))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "brush":
        p.setBrush(ink)
        p.drawEllipse(QRectF(5, 5, 8, 8))        # точка = мазок
    elif kind == "rect":
        p.drawRect(QRectF(3, 4, 12, 10))
    elif kind == "ellipse":
        p.drawEllipse(QRectF(3, 4, 12, 10))
    elif kind == "polygon":
        p.drawPolygon(QPolygonF([QPointF(9, 3), QPointF(15, 8), QPointF(12, 15),
                                 QPointF(6, 15), QPointF(3, 8)]))
    else:                                        # лассо — незамкнутая петля
        path = QPainterPath(QPointF(4, 14))
        path.cubicTo(QPointF(0, 4), QPointF(18, 2), QPointF(12, 10))
        path.cubicTo(QPointF(8, 15), QPointF(5, 9), QPointF(9, 8))
        p.drawPath(path)
    p.end()
    return QIcon(pm)


class BrushPanel(QWidget):
    """Сигналы: mode_toggled(on), layer_changed(key), radius_changed(m),
    erase_toggled(on), undo_requested(), redo_requested()."""

    mode_toggled = Signal(bool)
    tool_changed = Signal(str)
    apply_shape = Signal()
    cancel_shape = Signal()
    layer_changed = Signal(str)
    radius_changed = Signal(float)
    erase_toggled = Signal(bool)
    undo_requested = Signal()
    redo_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sw_mode = Switch((33, 150, 243), self)
        self.sw_mode.setToolTip(tr("brush.mode_tip"))
        self.sw_mode.toggled.connect(self.mode_toggled)
        head = QHBoxLayout()
        head.addWidget(self.sw_mode)
        head.addWidget(QLabel(tr("brush.mode")), 1)

        # инструмент: кисть или фигура-заливка (контур правится ручками, Enter применяет)
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
            b.setIcon(_tool_icon(name, ink))     # иконки рисуем сами: юникод-глифы
            b.setToolTip(tr(tip))                # вроде ⬠ есть не в каждом шрифте
            b.setCheckable(True)
            b.setChecked(name == "brush")
            b.setProperty("tool", name)
            self.tools.addButton(b)
            t_row.addWidget(b)
        t_row.addStretch(1)
        self.tools.buttonClicked.connect(
            lambda b: self.tool_changed.emit(b.property("tool")))

        self.cmb_layer = QComboBox()
        self.cmb_layer.setToolTip(tr("brush.layer_tip"))
        # длинные имена флагов не должны раздвигать левую колонку — карта дороже
        self.cmb_layer.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.cmb_layer.setMinimumContentsLength(8)
        self.cmb_layer.currentIndexChanged.connect(self._on_layer)
        lay_row = QHBoxLayout()
        lay_row.addWidget(QLabel(tr("brush.layer")))
        lay_row.addWidget(self.cmb_layer, 1)

        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setRange(5, 500)                # метры радиуса
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
        self.sw_erase.toggled.connect(self.erase_toggled)
        e_row = QHBoxLayout()
        e_row.addWidget(self.sw_erase)
        e_row.addWidget(QLabel(tr("brush.erase")), 1)

        # классические стрелки из стиля ОС вместо подписей: компактно и узнаваемо
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

        # применение контура фигуры (те же Enter / Esc)
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

        self.btn_save = QPushButton(tr("brush.save"))
        self.btn_save.setToolTip(tr("brush.save_tip"))
        self.btn_save.clicked.connect(self.save_requested)
        self.btn_save.setEnabled(False)          # без правок сохранять нечего

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addLayout(t_row)
        lay.addLayout(lay_row)
        lay.addLayout(r_row)
        lay.addLayout(e_row)
        lay.addLayout(s_row)
        lay.addLayout(u_row)
        lay.addWidget(self.lbl_state)
        lay.addWidget(self.btn_save)
        lay.addStretch(1)
        self._on_radius(self.sld.value())

    # ---------- наполнение ----------

    def populate(self, keys: list[tuple[str, str]]):
        """keys — [(key, отображаемое имя)] всех слоёв тиров и usage карты."""
        self.cmb_layer.blockSignals(True)
        self.cmb_layer.clear()
        for key, name in keys:
            self.cmb_layer.addItem(name, key)
        self.cmb_layer.blockSignals(False)
        if keys:
            self.layer_changed.emit(self.cmb_layer.currentData())

    def clear(self):
        self.cmb_layer.blockSignals(True)
        self.cmb_layer.clear()
        self.cmb_layer.blockSignals(False)
        self.sw_mode.setChecked(False)
        self.set_history(0, 0)
        self.set_dirty(0)

    def layer_key(self) -> str | None:
        return self.cmb_layer.currentData()

    def select_layer(self, key: str):
        i = self.cmb_layer.findData(key)
        if i >= 0 and i != self.cmb_layer.currentIndex():
            self.cmb_layer.setCurrentIndex(i)

    def radius(self) -> float:
        return float(self.sld.value())

    def set_shape_ready(self, ready: bool):
        """Есть ли контур, который можно залить."""
        self.btn_apply.setEnabled(ready)
        self.btn_cancel.setEnabled(ready)

    def tool(self) -> str:
        b = self.tools.checkedButton()
        return b.property("tool") if b else "brush"

    def set_history(self, undo: int, redo: int):
        self.btn_undo.setEnabled(undo > 0)
        self.btn_redo.setEnabled(redo > 0)

    def set_dirty(self, cells: int):
        """Сколько ячеек отличается от файла на диске (0 — правок нет)."""
        self.btn_save.setEnabled(bool(cells))
        if cells:
            self.lbl_state.setText(tr("brush.dirty", n=f"{cells:,}".replace(",", " ")))
        else:
            self.lbl_state.setText(tr("brush.saved"))

    def _on_layer(self, _i: int):
        key = self.cmb_layer.currentData()
        if key:
            self.layer_changed.emit(key)

    def _on_radius(self, v: int):
        self.lbl_radius.setText(tr("brush.radius_m", m=v))
        self.radius_changed.emit(float(v))
