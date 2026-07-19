"""Диалог ПЕРЕКОНФИГУРАЦИИ проекта (из редактора, кнопка «Открыть/Настроить»).

Точка входа приложения — приветственное окно (`light.welcome_window`); этот диалог остаётся
для смены источника/миссии уже открытого проекта. Отвечает за ПОДКЛЮЧЕНИЕ (папка / SFTP),
дальнейшую настройку и сборку проекта делает общий `ConfigurePanel`. Ветки «PROJECTS» здесь
больше нет — недавние проекты грузятся во вкладке «Недавние» приветственного окна."""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from light import project as P
from light.configure_panel import ConfigurePanel
from light.providers import ProviderError, make_provider, sftp_available


class ProjectConfigDialog(QDialog):
    """Возвращает готовый `P.Project` через `.result_project` (или None при отмене)."""

    def __init__(self, parent=None, existing: P.Project | None = None):
        super().__init__(parent)
        self.setWindowTitle("Настройка проекта")
        self.resize(640, 680)
        self.result_project = None

        # --- источник ---
        self.kind_combo = QComboBox()
        self.kind_combo.addItem("Папка (сервер DayZ)", "local")
        if sftp_available():
            self.kind_combo.addItem("SFTP (сервер DayZ)", "sftp")
        self.kind_combo.currentIndexChanged.connect(self._on_kind)

        # локальный источник
        self.folder_edit = QLineEdit()
        folder_button = QPushButton("Открыть папку")
        folder_button.clicked.connect(self._pick_folder)
        local_row = QHBoxLayout()
        local_row.addWidget(self.folder_edit, 1)
        local_row.addWidget(folder_button)
        self.local_widget = QWidget()
        local_form = QFormLayout(self.local_widget)
        local_form.setContentsMargins(0, 0, 0, 0)
        local_form.addRow("Корневая папка:", local_row)

        # SFTP источник
        self.sftp_widget = QWidget()
        sftp_form = QFormLayout(self.sftp_widget)
        sftp_form.setContentsMargins(0, 0, 0, 0)
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
        sftp_form.addRow("Хост:", self.host_edit)
        sftp_form.addRow("Порт:", self.port_spin)
        sftp_form.addRow("Пользователь:", self.user_edit)
        sftp_form.addRow("Пароль:", self.password_edit)
        sftp_form.addRow("Ключ:", self.key_edit)
        sftp_form.addRow("Папка сервера DayZ:", self.root_edit)
        self.sftp_widget.hide()

        self.connect_button = QPushButton("Подключить")
        self.connect_button.clicked.connect(self._connect)

        source_group = QGroupBox("Источник данных")
        source_layout = QVBoxLayout(source_group)
        source_layout.addWidget(self.kind_combo)
        source_layout.addWidget(self.local_widget)
        source_layout.addWidget(self.sftp_widget)
        source_layout.addWidget(self.connect_button)

        # --- общая панель настройки ---
        self.panel = ConfigurePanel()
        self.panel.ready_changed.connect(self._on_ready)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(source_group)
        layout.addWidget(self.panel, 1)
        layout.addWidget(self.buttons)

        if existing:
            self._prefill(existing)
        self._on_ready(self.panel.is_ready())

    # ---------- источник ----------

    def _on_kind(self, *_args) -> None:
        kind = self.kind_combo.currentData()
        self.local_widget.setVisible(kind == "local")
        self.sftp_widget.setVisible(kind == "sftp")

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Корневая папка сервера или миссии")
        if folder:
            self.folder_edit.setText(folder)

    def _provider_cfg(self) -> dict:
        if self.kind_combo.currentData() == "sftp":
            return {
                "kind": "sftp",
                "host": self.host_edit.text().strip(),
                "port": self.port_spin.value(),
                "user": self.user_edit.text().strip(),
                "password": self.password_edit.text() or None,
                "key_path": self.key_edit.text().strip() or None,
                "root": self.root_edit.text().strip() or "/",
            }
        return {"kind": "local", "root": self.folder_edit.text().strip()}

    def _connect(self) -> None:
        config = self._provider_cfg()
        try:
            provider = make_provider(config)
        except (ProviderError, KeyError, OSError) as error:
            QMessageBox.warning(self, "Источник", f"Не удалось: {error}")
            self.panel.clear()
            return
        self.panel.set_provider(provider, config)

    # ---------- prefill / готовность / OK ----------

    def _prefill(self, project: P.Project) -> None:
        config = project.provider_cfg
        index = self.kind_combo.findData(config.get("kind", "local"))
        if index >= 0:
            self.kind_combo.setCurrentIndex(index)
        if config.get("kind") == "sftp":
            self.host_edit.setText(config.get("host", ""))
            self.port_spin.setValue(int(config.get("port", 22)))
            self.user_edit.setText(config.get("user", ""))
            self.root_edit.setText(config.get("root", "/"))
        else:
            self.folder_edit.setText(config.get("root", ""))
        self.panel.project_name_edit.setText(project.name)
        self._on_kind()

    def _on_ready(self, ready: bool) -> None:
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(ready)

    def _accept(self) -> None:
        project = self.panel.build_project()
        if project is not None:
            self.result_project = project
            self.accept()
