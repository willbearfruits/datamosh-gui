#!/usr/bin/env python3
"""Entry point for the Datamosh GUI application."""

import sys

from gui.app import create_app, sanitize_qt_plugin_env
from gui.shortcuts import register_shortcuts


def main() -> int:
    # Ensure Qt plugin env is sanitized before importing modules that may import cv2.
    sanitize_qt_plugin_env()
    from gui.main_window import MainWindow

    app = create_app()
    window = MainWindow()
    register_shortcuts(window)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
