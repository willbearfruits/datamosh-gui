#!/usr/bin/env python3
"""Entry point for the Datamosh GUI application."""

import sys

from gui.app import create_app
from gui.main_window import MainWindow
from gui.shortcuts import register_shortcuts


def main() -> int:
    app = create_app()
    window = MainWindow()
    register_shortcuts(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
