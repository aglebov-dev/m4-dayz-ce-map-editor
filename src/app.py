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

    # Устанавливаем иконку приложения
    icon_path = os.path.join(os.path.dirname(__file__), "..", "app_icon_high.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    win = LightMainWindow()
    # при старте — приветственное окно: выбор способа загрузки проекта вкладками
    welcome = WelcomeWindow(win)
    if welcome.exec() and welcome.result_project:
        win.open_project(welcome.result_project)
        win.show()
        sys.exit(app.exec())
    else:
        sys.exit()

if __name__ == "__main__":
    main()
