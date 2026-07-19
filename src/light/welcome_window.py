"""Приветственное окно — точка входа: выбор СПОСОБА загрузки проекта вкладками.

Перебирает коллекцию `light.sources.SOURCES`, для каждого источника по `availability()`
решает, как показать вкладку (единая политика — `_add_source`). Когда источник эмитит
`project_ready`, окно запоминает проект в `result_project` и закрывается (accept).

Вкладки собраны в карточку по центру окна («со смещением в центр»)."""
from __future__ import annotations

import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QSizePolicy, QTabWidget, QVBoxLayout,
    QWidget,
)

from core import i18n
from core.i18n import tr
from light.sources import SOURCES
from light.sources.base import Availability, ProjectSource

_CARD_WIDTH = 720


class WelcomeWindow(QDialog):
    """Возвращает готовый `light.project.Project` через `.result_project` (None при отмене).
    Если сменили язык (`.relaunch == True`) — app.py переоткрывает окно на новой локали."""

    def __init__(self, parent=None, source_classes: list[type[ProjectSource]] | None = None,
                 settings=None):
        super().__init__(parent)
        self.setWindowTitle("M4 DayZ CE Map Editor")
        self.resize(900, 640)
        self.result_project = None
        self.relaunch = False
        self._settings = settings                # для смены языка (может быть None)
        self._sources: list[ProjectSource] = []

        # --- центрирующая раскладка: карточка по центру окна ---
        outer = QVBoxLayout(self)
        outer.addStretch(1)
        center_row = QHBoxLayout()
        center_row.addStretch(1)
        card = QWidget()
        card.setMaximumWidth(_CARD_WIDTH)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        center_row.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        center_row.addStretch(1)
        outer.addLayout(center_row, 0)
        outer.addStretch(1)

        card_layout = QVBoxLayout(card)
        card_layout.addWidget(self._build_header())

        self.tabs = QTabWidget()
        card_layout.addWidget(self.tabs, 1)

        for source_class in (source_classes or SOURCES):
            source = source_class(self)
            source.project_ready.connect(self._on_project_ready)
            self._sources.append(source)
            self._add_source(source)

        self._select_first_available()

    # ---------- заголовок ----------

    def _build_header(self) -> QWidget:
        header = QWidget()
        layout = QHBoxLayout(header)
        layout.setContentsMargins(0, 0, 0, 8)

        icon_path = os.path.join(os.path.dirname(__file__), "..", "..", "app_icon_high.ico")
        if os.path.exists(icon_path):
            logo = QLabel()
            logo.setPixmap(self._sharp_icon(icon_path, 48))
            layout.addWidget(logo)

        title = QLabel(f"<b style='font-size:16pt'>M4 DayZ CE Map Editor</b><br>"
                       f"<span style='color:gray'>{tr('welcome.subtitle')}</span>")
        layout.addWidget(title)
        layout.addStretch(1)
        # переключатель языка — верх-право от заголовка
        if self._settings is not None:
            self.cmb_lang = QComboBox()
            self.cmb_lang.addItems(i18n.available())
            self.cmb_lang.setCurrentText(self._settings.lang)
            self.cmb_lang.setToolTip(tr("lang.tip"))
            self.cmb_lang.currentTextChanged.connect(self._on_lang)
            layout.addWidget(self.cmb_lang, 0, Qt.AlignmentFlag.AlignTop)
        return header

    def _on_lang(self, lang: str) -> None:
        """Смена языка: сохранить и переоткрыть окно на новой локали (app.py)."""
        if not self._settings or lang == self._settings.lang:
            return
        self._settings.lang = lang
        self._settings.save()
        i18n.load(lang)
        self.relaunch = True
        self.reject()

    def _sharp_icon(self, path: str, logical_size: int):
        """Чёткий логотип из .ico: берём кадр под физический размер (logical×DPI) — Qt
        выбирает ближайший встроенный размер и уменьшает, а не растягивает мелкий."""
        ratio = max(1.0, self.devicePixelRatioF())
        pixmap = QIcon(path).pixmap(QSize(round(logical_size * ratio),
                                          round(logical_size * ratio)))
        pixmap.setDevicePixelRatio(ratio)     # рисуется в logical_size логических px, резко
        return pixmap

    # ---------- политика отображения источников ----------

    def _add_source(self, source: ProjectSource) -> None:
        """ЕДИНАЯ точка политики: доступный источник — активная вкладка; недоступный —
        вкладка заблокирована, причина в подсказке и на самой вкладке. Менять «как
        показывать недоступное» — только здесь."""
        availability = source.availability()
        if availability.ok:
            self.tabs.addTab(source.build_widget(), tr(source.title))
        else:
            index = self.tabs.addTab(
                self._unavailable_placeholder(availability), tr(source.title))
            self.tabs.setTabEnabled(index, False)
            self.tabs.setTabToolTip(index, availability.reason)

    def _unavailable_placeholder(self, availability: Availability) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addStretch(1)
        label = QLabel(tr("welcome.unavailable", reason=availability.reason))
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        label.setStyleSheet("color: gray;")
        layout.addWidget(label)
        layout.addStretch(1)
        return widget

    def _select_first_available(self) -> None:
        for index in range(self.tabs.count()):
            if self.tabs.isTabEnabled(index):
                self.tabs.setCurrentIndex(index)
                return

    # ---------- результат ----------

    def _on_project_ready(self, project) -> None:
        self.result_project = project
        self.accept()
