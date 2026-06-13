"""QApplication setup with dark theme."""

import os
import sys

from PySide6.QtCore import QLibraryInfo
from PySide6.QtWidgets import QApplication

from gui.ffmpeg_env import suppress_subprocess_console
from gui.theme import STYLESHEET, make_dark_palette
from gui.version import get_version


def sanitize_qt_plugin_env() -> None:
    """Prefer PySide6 Qt plugins over OpenCV's bundled Qt plugins."""
    cv2_qt_marker = "cv2/qt/plugins"
    for key in ("QT_QPA_PLATFORM_PLUGIN_PATH", "QT_PLUGIN_PATH"):
        val = os.environ.get(key, "")
        if cv2_qt_marker in val:
            os.environ.pop(key, None)

    plugins_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
    if plugins_dir:
        os.environ.setdefault("QT_PLUGIN_PATH", plugins_dir)
        os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", f"{plugins_dir}/platforms")


def create_app(argv: list[str] | None = None) -> QApplication:
    """Create and configure the QApplication instance."""
    if argv is None:
        argv = sys.argv
    sanitize_qt_plugin_env()
    suppress_subprocess_console()  # no ffmpeg/ffprobe console flashes on Windows
    app = QApplication(argv)
    app.setApplicationName("Datamosh")
    app.setApplicationVersion(get_version())
    app.setOrganizationName("datamosh")
    app.setStyle("Fusion")
    app.setPalette(make_dark_palette())
    app.setStyleSheet(STYLESHEET)
    return app
