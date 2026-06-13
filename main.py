#!/usr/bin/env python3
"""Entry point for the Datamosh GUI application."""

import sys

from gui.app import create_app, sanitize_qt_plugin_env
from gui.ffmpeg_env import ensure_ffmpeg_on_path, missing_ffmpeg_tools
from gui.shortcuts import register_shortcuts


def main() -> int:
    # Ensure Qt plugin env is sanitized before importing modules that may import cv2.
    sanitize_qt_plugin_env()
    # Make a bundled ffmpeg (frozen builds) discoverable before any worker runs.
    ensure_ffmpeg_on_path()
    from gui.main_window import MainWindow

    app = create_app()
    window = MainWindow()
    register_shortcuts(window)
    window.show()

    missing = missing_ffmpeg_tools()
    if missing:
        from PySide6.QtWidgets import QMessageBox

        tools = " and ".join(missing)
        QMessageBox.warning(
            window,
            "FFmpeg not found",
            f"Datamosh needs {tools} to import, preview, and render clips, but "
            f"{'they were' if len(missing) > 1 else 'it was'} not found on your PATH.\n\n"
            "Install FFmpeg and make sure it is on PATH:\n"
            "  • Windows:  winget install Gyan.FFmpeg   (then reopen the app)\n"
            "  • macOS:    brew install ffmpeg\n"
            "  • Linux:    sudo apt install ffmpeg\n\n"
            "Imports and renders will fail until FFmpeg is available.",
        )
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
