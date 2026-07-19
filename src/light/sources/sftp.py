"""Источник «Через SFTP» — папка сервера DayZ на удалённой машине.

Недоступен без paramiko — тогда `availability()` вернёт причину, и приветственное окно
покажет вкладку заблокированной. Подключение → SftpProvider, дальше общий `ConfigurePanel`."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from light.configure_panel import ConfigurePanel
from light.providers import ProviderError, SftpProvider, sftp_available
from light.sources.base import Availability, ProjectSource


class SftpProjectSource(ProjectSource):
    id = "sftp"
    title = "Через SFTP"

    def availability(self) -> Availability:
        if sftp_available():
            return Availability.available()
        return Availability.unavailable("не установлен paramiko (pip install paramiko)")

    def build_widget(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        form = QFormLayout()
        self.host_edit = QLineEdit()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1, 65535)
        self.port_spin.setValue(22)
        self.user_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit = QLineEdit()
        self.root_edit = QLineEdit()
        self.root_edit.setText("/")
        form.addRow("Хост:", self.host_edit)
        form.addRow("Порт:", self.port_spin)
        form.addRow("Пользователь:", self.user_edit)
        form.addRow("Пароль:", self.password_edit)
        form.addRow("Ключ:", self.key_edit)
        form.addRow("Папка сервера DayZ:", self.root_edit)
        layout.addLayout(form)

        self.connect_button = QPushButton("Подключить")
        self.connect_button.clicked.connect(self._connect)
        layout.addWidget(self.connect_button)

        self.panel = ConfigurePanel()
        self.panel.ready_changed.connect(self._on_ready)
        layout.addWidget(self.panel, 1)

        self.create_button = QPushButton("Загрузить проект")
        self.create_button.setEnabled(False)
        self.create_button.clicked.connect(self._create)
        layout.addWidget(self.create_button)
        return widget

    def _provider_cfg(self) -> dict:
        return {
            "kind": "sftp",
            "host": self.host_edit.text().strip(),
            "port": self.port_spin.value(),
            "user": self.user_edit.text().strip(),
            "password": self.password_edit.text() or None,
            "key_path": self.key_edit.text().strip() or None,
            "root": self.root_edit.text().strip() or "/",
        }

    def _connect(self) -> None:
        config = self._provider_cfg()
        try:
            provider = SftpProvider(
                config["host"], config["user"], config["root"],
                port=int(config["port"]), password=config["password"],
                key_path=config["key_path"])
        except (ProviderError, KeyError, OSError) as error:
            QMessageBox.warning(self.panel, "SFTP", f"Не удалось: {error}")
            self.panel.clear()
            return
        self.panel.set_provider(provider, config)

    def _on_ready(self, ready: bool) -> None:
        self.create_button.setEnabled(ready)

    def _create(self) -> None:
        project = self.panel.build_project()
        if project is not None:
            self.emit_project(project)
