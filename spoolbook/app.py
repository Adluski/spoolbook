"""Application entry point: build the QApplication, apply the theme, show the
main window."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .config import APP_NAME
from .ui.main_window import MainWindow
from .ui.theme import BASE_POINT_SIZE, UI_FONT_FAMILY, build_stylesheet


def build_application(argv: list[str] | None = None) -> QApplication:
    app = QApplication.instance() or QApplication(argv or sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("Spoolbook")

    font = QFont(UI_FONT_FAMILY, BASE_POINT_SIZE)
    font.setStyleHint(QFont.SansSerif)
    app.setFont(font)

    app.setStyleSheet(build_stylesheet())
    return app


def main() -> int:
    app = build_application()
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
