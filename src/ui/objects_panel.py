"""Инспектор объектов: клик выбирает БЛИЖАЙШЕЕ здание в радиусе; его эффективные
тиры/usage — строками со свитчами, один в один как в инспекторе слоёв."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from core.areaflags import AreaFlags
from core.i18n import tr
from ui.inspector_panel import FlagRow
from ui.layers_panel import Switch


class ObjectsInspectorPanel(QWidget):
    layer_toggle_requested = Signal(str, bool)   # (ключ слоя, видимость) — как у инспектора слоёв

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sw_active = Switch((76, 175, 80), self)
        self.sw_active.setChecked(True)
        head = QHBoxLayout()
        head.addWidget(self.sw_active)
        head.addWidget(QLabel(tr("inspector.toggle")))
        head.addStretch(1)

        self.info = QLabel(tr("objects.hint"))
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)

        self._flags_lay = QVBoxLayout()
        self._flags_lay.setSpacing(0)
        self._rows: list[FlagRow] = []
        self._last: tuple | None = None          # (b, af, colors)
        self._visible: dict[str, bool] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addWidget(self.info)
        lay.addLayout(self._flags_lay)
        lay.addStretch(1)

    def is_active(self) -> bool:
        return self.sw_active.isChecked()

    def clear(self):
        self._last = None
        self._clear_rows()
        self.info.setText(tr("objects.hint"))

    # ---------- данные ----------

    def show_building(self, b: dict | None, af: AreaFlags,
                      colors: dict[str, tuple[int, int, int]],
                      visible: dict[str, bool] | None = None):
        if visible is not None:
            self._visible = dict(visible)
        self._last = (b, af, colors)
        self._rebuild()

    def update_layer_state(self, key: str, visible: bool):
        """Синхронизация из панели слоёв (в т.ч. эхо собственного тогла)."""
        self._visible[key] = visible
        row = next((r for r in self._rows if r.key == key), None)
        if row and row.sw.isChecked() != visible:
            row.sw.blockSignals(True)
            row.sw.setChecked(visible)
            row.sw.blockSignals(False)

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
        b, af, colors = self._last
        if b is None:
            self.info.setText(f"<i>{tr('objects.empty')}</i>")
            return
        self.info.setText(
            f"<b>{b['name']}</b><br>"
            f"X {b['x']:.1f}&nbsp;&nbsp;Z {b['z']:.1f}<br>"
            f"{tr('inspector.bld_info', dist=f'{b['dist']:.1f}', lootmax=b['lootmax'], points=b['points'])}<br>"
            f"<span style='color: gray;'>{tr('inspector.origin_legend')}</span>")

        def src(bit: int, gmask: int, cmask: int) -> str:
            g, c = gmask >> bit & 1, cmask >> bit & 1
            return "g+c" if g and c else "g" if g else "c"

        hits = ([("tier", n, bit, b["group_v"], b["cell_v"])
                 for bit, n in enumerate(af.values) if b["eff_v"] >> bit & 1]
                + [("usage", n, bit, b["group_u"], b["cell_u"])
                   for bit, n in enumerate(af.usages) if b["eff_u"] >> bit & 1])
        for kind, name, bit, gmask, cmask in hits:
            key = f"{kind}:{name}"
            fr = FlagRow(key, f"{name}  ({src(bit, gmask, cmask)})",
                         colors.get(key, (200, 200, 200)),
                         self._visible.get(key, False), self)
            self._rows.append(fr)
            self._flags_lay.addWidget(fr)
        if not hits:
            self._flags_lay.addWidget(QLabel(f"<i>{tr('inspector.none')}</i>"))
