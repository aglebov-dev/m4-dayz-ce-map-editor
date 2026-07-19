"""CE Editor Light — точка входа. Сначала окно проекта, затем редактор."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from light.main_window import LightMainWindow
from light.welcome_window import WelcomeWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("m4 dayz ce map editor")

    # Иконка приложения — из app_icon_high.ico (мультиразмерный .ico)
    icon_path = os.path.join(os.path.dirname(__file__), "..", "app_icon_high.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = LightMainWindow()
    # при старте — приветственное окно: выбор способа загрузки. Если проект не открылся
    # (нет карты / файл повреждён) — остаёмся на диалоге, редактор не показываем.
    while True:
        welcome = WelcomeWindow(win)
        if not (welcome.exec() and welcome.result_project):
            sys.exit()
        if win.open_project(welcome.result_project):
            break
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
