"""Инспектор точки: клик по карте — координаты, ячейка, и попавшие в точку тиры/usage
списком со свитчами (синхронны с панелью «Слои»). Режим: все флаги или только включённые."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.areaflags import AreaFlags
from core.i18n import tr
from ui.layers_panel import Switch


class FlagRow(QWidget):
    """Строка флага в точке: свитч видимости слоя + цвет + имя."""

    def __init__(self, key: str, name: str, color: tuple[int, int, int],
                 checked: bool, panel: "InspectorPanel"):
        super().__init__(panel)
        self.key = key
        self.sw = Switch(color, self)
        self.sw.setChecked(checked)
        self.sw.setToolTip(tr("layers.toggle_tip"))
        self.sw.toggled.connect(lambda ch: panel.layer_toggle_requested.emit(key, ch))
        square = QLabel(self)
        pm = QPixmap(12, 12)
        pm.fill(QColor(*color))
        square.setPixmap(pm)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.addWidget(self.sw)
        lay.addWidget(square)
        lay.addWidget(QLabel(name, self), 1)


class InspectorPanel(QWidget):
    layer_toggle_requested = Signal(str, bool)   # (ключ слоя, видимость)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sw_active = Switch((76, 175, 80), self)
        self.sw_active.setChecked(True)
        head = QHBoxLayout()
        head.addWidget(self.sw_active)
        head.addWidget(QLabel(tr("inspector.toggle")))
        head.addStretch(1)

        self.sw_only_visible = Switch((33, 150, 243), self)
        self.sw_only_visible.setChecked(False)
        self.sw_only_visible.toggled.connect(lambda _: self._rebuild())
        mode = QHBoxLayout()
        mode.addWidget(self.sw_only_visible)
        mode.addWidget(QLabel(tr("inspector.only_visible")))
        mode.addStretch(1)

        self.info = QLabel(tr("inspector.hint"))
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)

        self._flags_lay = QVBoxLayout()
        self._flags_lay.setSpacing(0)
        self._rows: list[FlagRow] = []
        # снимок последней точки для перестроения при смене режима/состояний
        self._last: tuple | None = None          # (x, z, af, colors)
        self._visible: dict[str, bool] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addLayout(mode)
        lay.addWidget(self.info)
        lay.addLayout(self._flags_lay)
        lay.addStretch(1)

    def is_active(self) -> bool:
        return self.sw_active.isChecked()

    # ---------- данные ----------

    def show_point(self, x: float, z: float, af: AreaFlags | None,
                   colors: dict[str, tuple[int, int, int]] | None = None,
                   visible: dict[str, bool] | None = None,
                   water: bool | None = None):
        """visible: key -> включён ли слой в панели «Слои» (для свитчей и режима).
        water: True=вода, False=суша, None=источника нет (проект CE Tool не загружен)."""
        if visible is not None:
            self._visible = dict(visible)
        self._last = (x, z, af, colors or {}, water)
        self._rebuild()

    def update_layer_state(self, key: str, visible: bool):
        """Синхронизация из панели слоёв (в т.ч. эхо собственного тогла)."""
        self._visible[key] = visible
        row = next((r for r in self._rows if r.key == key), None)
        if row and row.sw.isChecked() != visible:
            row.sw.blockSignals(True)
            row.sw.setChecked(visible)
            row.sw.blockSignals(False)
        if self.sw_only_visible.isChecked():     # в режиме "только включённые" состав меняется
            self._rebuild()

    # ---------- отрисовка ----------

    def _clear_rows(self):
        self._rows.clear()
        while self._flags_lay.count():
            it = self._flags_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _rebuild(self):
        self._clear_rows()
        if not self._last:
            return
        x, z, af, colors, water = self._last
        head = f"<b>X {x:.1f}&nbsp;&nbsp;Z {z:.1f}</b>"
        if af is None:
            self.info.setText(head + f"<br><i>{tr('inspector.no_af')}</i>")
            return
        if not (0 <= x < af.size_x and 0 <= z < af.size_y):
            self.info.setText(head + f"<br><i>{tr('inspector.out')}</i>")
            return
        col = int(x / af.cell_size)
        row = int(z / af.cell_size)
        idx = row * af.grid_x + col
        umask = int(af.usage[idx])
        tmask = int(af.tier[idx])
        water_line = ""
        if water:                                # water-fresh = пресная вода (пруды),
            water_line = "<br>" + tr("inspector.water")   # не море; сушу не утверждаем
        self.info.setText(
            f"{head}<br>"
            f"{tr('inspector.cell', col=col, row=row)}<br>"
            f"{tr('inspector.masks', u=f'{umask:08X}', v=f'{tmask:02X}')}"
            f"{water_line}")

        only_on = self.sw_only_visible.isChecked()
        hits = ([("tier", n) for b, n in enumerate(af.values) if tmask >> b & 1]
                + [("usage", n) for b, n in enumerate(af.usages) if umask >> b & 1])
        shown = 0
        for kind, name in hits:
            key = f"{kind}:{name}"
            on = self._visible.get(key, False)
            if only_on and not on:
                continue
            fr = FlagRow(key, name, colors.get(key, (200, 200, 200)), on, self)
            self._rows.append(fr)
            self._flags_lay.addWidget(fr)
            shown += 1
        if not shown:
            lbl = QLabel(f"<i>{tr('inspector.none')}</i>")
            self._flags_lay.addWidget(lbl)
