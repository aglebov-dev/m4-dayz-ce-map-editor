"""Панель слоёв: тиры и usage-флаги. Свитч-тогл в цвете слоя, смена цвета кликом по
квадратику, кнопки все/ничего в заголовке каждого раздела."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractButton, QComboBox, QHBoxLayout, QLabel, QScrollArea, QSlider,
    QToolButton, QVBoxLayout, QWidget,
)

from core.areaflags import AreaFlags
from core.i18n import tr

TRACK_OFF = QColor(140, 140, 140)


class Switch(QAbstractButton):
    """iOS-подобный тогл; включённый трек красится цветом слоя."""

    def __init__(self, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._color = QColor(*color)

    def set_color(self, rgb: tuple[int, int, int]):
        self._color = QColor(*rgb)
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(27, 14)

    def paintEvent(self, _ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        track = self._color if self.isChecked() else TRACK_OFF
        if not self.isEnabled():
            track = QColor(track.red(), track.green(), track.blue(), 70)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        d = r.height() - 4
        x = r.right() - d - 2 if self.isChecked() else r.left() + 2
        p.setBrush(QColor(255, 255, 255, 255 if self.isEnabled() else 140))
        p.drawEllipse(x, r.top() + 2, d, d)


class LayerRow(QWidget):
    """Строка слоя: свитч, квадратик цвета (клик = сменить цвет), имя (счётчик ячеек)."""

    def __init__(self, key: str, name: str, color: tuple[int, int, int],
                 count: int, panel: "LayersPanel"):
        super().__init__(panel)
        self.key = key
        self._panel = panel
        self.active = False
        # без WA_StyledBackground фон из styleSheet у QWidget-наследника не рисуется
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.btn = Switch(color, self)
        self.btn.setToolTip(tr("layers.toggle_tip"))
        self.btn.toggled.connect(lambda ch: panel.layer_toggled.emit(self.key, ch))

        self.swatch = QToolButton(self)
        self.swatch.setAutoRaise(True)
        self.swatch.setToolTip(tr("layers.color_tip"))
        self.swatch.clicked.connect(lambda: panel.color_clicked.emit(self.key))
        self._set_swatch(color)

        self.text = QLabel(f"{name}  ({count:,})".replace(",", " "), self)
        self.text.setToolTip(tr("layers.zones_tip"))
        # пустой слой (0 ячеек) НЕ отключаем: в редакторе на него можно рисовать —
        # включаем показ и красим кистью. Серый текст остаётся как пометка «пусто».
        self._enabled = True
        if count == 0:
            self.text.setStyleSheet("color: gray;")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.addWidget(self.btn)
        lay.addWidget(self.swatch)
        lay.addWidget(self.text, 1)
        # «×» удалить флаг — только в редакторе и только для тиров/usage
        if getattr(panel, "allow_add_flag", False) and key.split(":", 1)[0] in (
                "tier", "usage"):
            self.btn_del = QToolButton(self)
            self.btn_del.setText("×")
            self.btn_del.setAutoRaise(True)
            self.btn_del.setToolTip(tr("layers.del_flag"))
            self.btn_del.clicked.connect(lambda: panel.del_flag_requested.emit(self.key))
            lay.addWidget(self.btn_del)

    def mousePressEvent(self, ev):
        """Клик по строке = выбрать слой (зоны, а в режиме кисти — слой рисования).
        Клик по свитчу/квадратику цвета сюда не доходит — их виджеты съедают событие,
        поэтому «показать слой» и «сменить цвет» выбор НЕ меняют."""
        if self._enabled:
            self._panel.layer_selected.emit(self.key)
        super().mousePressEvent(ev)

    def set_active(self, on: bool):
        """Подсветка активного слоя кисти."""
        self.active = on
        self.setStyleSheet(
            "background: rgba(33, 150, 243, 70); border-radius: 3px;" if on else "")
        f = self.text.font()
        f.setBold(on)
        self.text.setFont(f)

    def set_color(self, rgb: tuple[int, int, int]):
        self.btn.set_color(rgb)
        self._set_swatch(rgb)

    def _set_swatch(self, rgb):
        pm = QPixmap(14, 14)
        pm.fill(QColor(*rgb))
        self.swatch.setIcon(pm)


class LayersPanel(QWidget):
    """Слои карты по разделам. Сигналы: layer_toggled(key, visible), color_clicked(key).
    Ключи: tier:<имя> / usage:<имя>."""

    layer_toggled = Signal(str, bool)
    color_clicked = Signal(str)
    layer_selected = Signal(str)         # клик по строке слоя — показать его зоны
    opacity_changed = Signal(str, int)   # (префикс раздела, значение 0..100)
    add_flag_requested = Signal(str)     # "usage"/"value" — добавить новый флаг (редактор)
    del_flag_requested = Signal(str)     # key слоя — удалить флаг (редактор)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[LayerRow] = []
        self._perm_sliders: list[QSlider] = []   # переживают clear()
        self.allow_add_flag = False              # редактор включает «＋» в заголовках
        self.setMinimumWidth(230)
        self._init_sliders()

        self._list_lay = QVBoxLayout()
        self._list_lay.setSpacing(0)
        inner = QWidget()
        inner.setLayout(self._list_lay)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(inner)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(scroll, 1)

    def _init_sliders(self):
        # слайдеры прозрачности разделов живут постоянно (populate их переставляет)
        self.sld_tier = self._make_slider("tier:", 45, tr("layers.tier_opacity_tip"))
        self.sld_usage = self._make_slider("usage:", 55, tr("layers.usage_opacity_tip"))

    def opacity(self, prefix: str) -> float:
        sld = self.sld_tier if prefix.startswith("tier") else self.sld_usage
        return sld.value() / 100.0

    def _make_slider(self, prefix: str, default: int, tip: str) -> QSlider:
        sld = QSlider(Qt.Orientation.Horizontal)
        sld.setRange(0, 100)
        sld.setValue(default)
        sld.setToolTip(tip)
        sld.valueChanged.connect(lambda v: self.opacity_changed.emit(prefix, v))
        self._perm_sliders.append(sld)
        return sld

    def populate(self, af: AreaFlags, counts_tier: list[int], counts_usage: list[int],
                 colors: dict[str, tuple[int, int, int]], tiers_on: bool = True):
        """colors: key -> RGB (с учётом переопределений)."""
        self.clear()
        self._add_header(tr("layers.tiers"), "tier:")
        self._list_lay.addWidget(self.sld_tier)
        for bit, name in enumerate(af.values):
            key = f"tier:{name}"
            self._add_row(key, name, colors[key], counts_tier[bit])
        self._add_header(tr("layers.usage"), "usage:")
        self._list_lay.addWidget(self.sld_usage)
        for bit, name in enumerate(af.usages):
            key = f"usage:{name}"
            self._add_row(key, name, colors[key], counts_usage[bit])
        self._list_lay.addStretch(1)
        if tiers_on:
            self.set_all(True, "tier:")

    def clear(self):
        self._rows.clear()
        while self._list_lay.count():
            it = self._list_lay.takeAt(0)
            w = it.widget()
            if w in self._perm_sliders:
                w.setParent(None)                # постоянные виджеты не убиваем
            elif w:
                w.deleteLater()

    def set_all(self, visible: bool, prefix: str = ""):
        for row in self._rows:
            if row.key.startswith(prefix) and row.btn.isEnabled():
                row.btn.setChecked(visible)

    def row(self, key: str) -> LayerRow:
        return next(r for r in self._rows if r.key == key)

    def set_active(self, key: str | None):
        """Подсветить активный слой кисти (None — снять подсветку со всех)."""
        self._active_key = key
        for r in self._rows:
            r.set_active(r.key == key)

    def active_key(self) -> str | None:
        return getattr(self, "_active_key", None)

    def _add_header(self, title: str, prefix: str):
        head = QWidget()
        lay = QHBoxLayout(head)
        lay.setContentsMargins(2, 6, 2, 2)
        lbl = QLabel(f"<b>{title}</b>")
        b_on = QToolButton(head)
        b_on.setText(tr("layers.all"))
        b_on.setAutoRaise(True)
        b_on.setToolTip(tr("layers.all_tip", section=title))
        b_on.clicked.connect(lambda: self.set_all(True, prefix))
        b_off = QToolButton(head)
        b_off.setText(tr("layers.none"))
        b_off.setAutoRaise(True)
        b_off.setToolTip(tr("layers.none_tip", section=title))
        b_off.clicked.connect(lambda: self.set_all(False, prefix))
        lay.addWidget(lbl, 1)
        lay.addWidget(b_on)
        lay.addWidget(b_off)
        # «＋» добавить флаг — только в редакторе и только для тиров/usage
        if self.allow_add_flag and prefix in ("tier:", "usage:"):
            kind = "value" if prefix == "tier:" else "usage"
            b_add = QToolButton(head)
            b_add.setText("+")
            b_add.setAutoRaise(True)
            b_add.setToolTip(tr("layers.add_flag"))
            b_add.clicked.connect(lambda: self.add_flag_requested.emit(kind))
            lay.addWidget(b_add)
        self._list_lay.addWidget(head)

    def _add_row(self, key, name, color, count):
        row = LayerRow(key, name, color, count, self)
        self._rows.append(row)
        self._list_lay.addWidget(row)


_MODES = ("points", "contour", "both")           # индексы cmb_mode ↔ режимы отображения


class BuildingsLayersPanel(LayersPanel):
    """Панель слоёв зданий по флагам (ключи `obj:…`). Режим отображения (точки / контур /
    точки+контур) — переключателем сверху; три раздельных слайдера прозрачности: точки
    (`objpoints:`), заливка контура (`obj:`), обводка контура (`objborder:`)."""

    mode_changed = Signal(str)                    # "points" | "contour" | "both"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout().insertWidget(0, self._mode_row())   # переключатель — над списком слоёв

    def _init_sliders(self):
        self.sld_points = self._make_slider("objpoints:", 100,
                                            tr("layers.bld_points_opacity_tip"))
        self.sld_obj = self._make_slider("obj:", 100, tr("layers.bld_opacity_tip"))
        self.sld_border = self._make_slider("objborder:", 100,
                                            tr("layers.bld_border_opacity_tip"))

    def opacity(self, prefix: str) -> float:
        return self.sld_obj.value() / 100.0       # заливка контура (совместимость сигнатуры)

    def _mode_row(self) -> QWidget:
        self.cmb_mode = QComboBox()
        self.cmb_mode.addItems([tr("bld.mode_points"), tr("bld.mode_contour"),
                                tr("bld.mode_both")])
        self.cmb_mode.setCurrentIndex(1)          # по умолчанию — контур
        self.cmb_mode.currentIndexChanged.connect(
            lambda i: self.mode_changed.emit(_MODES[i]))
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(4, 4, 4, 0)
        lay.addWidget(QLabel(tr("bld.mode")))
        lay.addWidget(self.cmb_mode, 1)
        return row

    def mode(self) -> str:
        return _MODES[self.cmb_mode.currentIndex()]

    def points_opacity(self) -> float:
        return self.sld_points.value() / 100.0

    def border_opacity(self) -> float:
        return self.sld_border.value() / 100.0

    def populate(self, objects: list[tuple[str, str, tuple[int, int, int], int]]):
        self.clear()
        if objects:
            self._add_header(tr("layers.buildings"), "obj:")
            # подписи-транзиенты (пересоздаются при populate); сами слайдеры — постоянные
            self._list_lay.addWidget(QLabel(tr("layers.bld_points")))
            self._list_lay.addWidget(self.sld_points)
            self._list_lay.addWidget(QLabel(tr("layers.bld_fill")))
            self._list_lay.addWidget(self.sld_obj)
            self._list_lay.addWidget(QLabel(tr("layers.bld_border")))
            self._list_lay.addWidget(self.sld_border)
            for key, name, color, count in objects:
                self._add_row(key, name, color, count)
        self._list_lay.addStretch(1)


class TerritoriesPanel(LayersPanel):
    """Панель территорий животных: слой на файл env/*_territories.xml (круги)."""

    def _init_sliders(self):
        self.sld_terr = self._make_slider("terr:", 100, tr("layers.terr_opacity_tip"))

    def opacity(self, prefix: str) -> float:
        return self.sld_terr.value() / 100.0

    def populate(self, items: list[tuple[str, str, tuple[int, int, int], int]]):
        """items: (key, имя, цвет, счётчик кругов)."""
        self.clear()
        if items:
            self._add_header(tr("layers.territories"), "terr:")
            self._list_lay.addWidget(self.sld_terr)
            for key, name, color, count in items:
                self._add_row(key, name, color, count)
        self._list_lay.addStretch(1)
