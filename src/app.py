"""CE Editor Light — точка входа. Сначала окно проекта, затем редактор."""
import faulthandler
import os
import sys
import traceback
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon

from core import i18n
from core.paths import paths
from core.workspace import Settings
from light.main_window import LightMainWindow
from light.welcome_window import WelcomeWindow

_crash_log = None


def _install_crash_logging():
    """Записать любой краш в `appdata/crash.log` — иначе в onefile-сборке (консоль
    отключена) и нативный segfault (висячий QWidget), и необработанное исключение в
    слоте Qt улетают молча. `faulthandler` ловит фатальные сигналы с Python-стеком;
    `sys.excepthook` — обычные исключения. Оба дописывают в один файл."""
    global _crash_log
    try:
        paths.ensure(paths.appdata)
        log_path = paths.appdata / "crash.log"
        _crash_log = open(log_path, "a", encoding="utf-8", buffering=1)
        faulthandler.enable(file=_crash_log, all_threads=True)
    except Exception:
        return

    def hook(exc_type, exc, tb):
        try:
            _crash_log.write(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S} "
                             f"unhandled exception ====\n")
            traceback.print_exception(exc_type, exc, tb, file=_crash_log)
            _crash_log.flush()
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook

    from PySide6.QtCore import qInstallMessageHandler, QtMsgType
    _label = {QtMsgType.QtDebugMsg: "DEBUG", QtMsgType.QtInfoMsg: "INFO",
              QtMsgType.QtWarningMsg: "WARNING", QtMsgType.QtCriticalMsg: "CRITICAL",
              QtMsgType.QtFatalMsg: "FATAL"}

    def qt_handler(mode, ctx, msg):
        try:
            sys.stderr.write(f"[Qt {_label.get(mode, '?')}] {msg}\n")
        except Exception:
            pass
        if mode in (QtMsgType.QtWarningMsg, QtMsgType.QtCriticalMsg,
                    QtMsgType.QtFatalMsg):
            try:
                _crash_log.write(f"\n==== {datetime.now():%Y-%m-%d %H:%M:%S} "
                                 f"Qt {_label.get(mode, '?')} ====\n{msg}\n")
                if ctx and ctx.file:
                    _crash_log.write(f"    at {ctx.file}:{ctx.line}\n")
                _crash_log.flush()
            except Exception:
                pass

    qInstallMessageHandler(qt_handler)


def main():
    _install_crash_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("m4 dayz ce map editor")

    icon_path = os.path.join(os.path.dirname(__file__), "..", "app_icon_high.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    paths.ensure(paths.appdata)
    settings = Settings(str(paths.settings_file))
    i18n.load(settings.lang)

    win = None
    while True:
        welcome = WelcomeWindow(settings=settings)
        welcome.exec()
        if welcome.relaunch:
            win = None
            continue
        if not welcome.result_project:
            sys.exit()
        if win is None:
            win = LightMainWindow()
        if win.open_project(welcome.result_project):
            break
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
