"""Инспектор зданий: показывает эффективные тиры/usage выбранного здания (свитчи, как в
инспекторе слоёв). Если в точке клика несколько зданий (высотки/наложение контуров) —
сверху появляется список-переключатель, по которому листаем конкретное здание."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from core.areaflags import AreaFlags
from core.i18n import tr
from ui.inspector_panel import FlagRow
from ui.layers_panel import Switch


class BuildingInspectorPanel(QWidget):
    """Сигналы: layer_toggle_requested(key, visible) — как у инспектора слоёв;
    building_picked(index) — выбрано конкретное здание из списка кандидатов."""

    layer_toggle_requested = Signal(str, bool)
    building_picked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.sw_active = Switch((76, 175, 80), self)
        self.sw_active.setChecked(True)
        head = QHBoxLayout()
        head.addWidget(self.sw_active)
        head.addWidget(QLabel(tr("inspector.toggle")))
        head.addStretch(1)

        self.cmb_pick = QComboBox(self)
        self.cmb_pick.currentIndexChanged.connect(self._on_pick)
        self.cmb_pick.hide()

        self.info = QLabel(tr("objects.hint"))
        self.info.setWordWrap(True)
        self.info.setTextFormat(Qt.TextFormat.RichText)

        self._flags_lay = QVBoxLayout()
        self._flags_lay.setSpacing(0)
        self._rows: list[FlagRow] = []
        self._cands: list[dict] = []
        self._af: AreaFlags | None = None
        self._colors: dict = {}
        self._visible: dict[str, bool] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.addLayout(head)
        lay.addWidget(self.cmb_pick)
        lay.addWidget(self.info)
        lay.addLayout(self._flags_lay)
        lay.addStretch(1)

    def is_active(self) -> bool:
        return self.sw_active.isChecked()

    def clear(self):
        self._cands = []
        self._set_combo([])
        self._clear_rows()
        self.info.setText(tr("objects.hint"))


    def show_buildings(self, cands: list[dict], af: AreaFlags,
                       colors: dict[str, tuple[int, int, int]],
                       visible: dict[str, bool] | None = None):
        """cands — список инфо-диктов зданий в точке клика (пустой = «рядом ничего»)."""
        if visible is not None:
            self._visible = dict(visible)
        self._af = af
        self._colors = colors
        self._cands = cands
        self._set_combo(cands)
        self._rebuild()
        if cands:
            self.building_picked.emit(cands[0]["index"])

    def update_layer_state(self, key: str, visible: bool):
        """Синхронизация из панели слоёв (в т.ч. эхо собственного тогла)."""
        self._visible[key] = visible
        row = next((r for r in self._rows if r.key == key), None)
        if row and row.sw.isChecked() != visible:
            row.sw.blockSignals(True)
            row.sw.setChecked(visible)
            row.sw.blockSignals(False)


    def _set_combo(self, cands: list[dict]):
        self.cmb_pick.blockSignals(True)
        self.cmb_pick.clear()
        for c in cands:
            self.cmb_pick.addItem(f"{c['name']}  ({c['dist']:.1f} m)")
        self.cmb_pick.setCurrentIndex(0 if cands else -1)
        self.cmb_pick.blockSignals(False)
        self.cmb_pick.setVisible(len(cands) > 1)

    def _on_pick(self, i: int):
        if 0 <= i < len(self._cands):
            self._rebuild()
            self.building_picked.emit(self._cands[i]["index"])

    def _current(self) -> dict | None:
        i = self.cmb_pick.currentIndex()
        if 0 <= i < len(self._cands):
            return self._cands[i]
        return self._cands[0] if self._cands else None


    def _clear_rows(self):
        self._rows.clear()
        while self._flags_lay.count():
            it = self._flags_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _rebuild(self):
        self._clear_rows()
        b = self._current()
        if b is None:
            self.info.setText(f"<i>{tr('objects.empty')}</i>")
            return
        af, colors = self._af, self._colors
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
