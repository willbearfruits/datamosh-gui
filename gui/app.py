"""QApplication setup with dark theme."""

import sys

from PySide6.QtWidgets import QApplication

from gui.theme import STYLESHEET, make_dark_palette


def create_app(argv: list[str] | None = None) -> QApplication:
    """Create and configure the QApplication instance."""
    if argv is None:
        argv = sys.argv
    app = QApplication(argv)
    app.setApplicationName("Datamosh")
    app.setOrganizationName("datamosh")
    app.setStyle("Fusion")
    app.setPalette(make_dark_palette())
    app.setStyleSheet(STYLESHEET)
    return app
