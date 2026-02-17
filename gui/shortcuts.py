"""QShortcut-based keyboard shortcut manager."""

from __future__ import annotations

import sys

from PySide6.QtGui import QKeySequence, QShortcut


def register_shortcuts(window) -> None:
    """Wire up all keyboard shortcuts on the main window."""
    from gui.main_window import MainWindow
    assert isinstance(window, MainWindow)

    _bind(window, "Ctrl+O", window.clip_panel.open_files)
    _bind(window, "Ctrl+Shift+O", window.clip_panel.open_files)
    _bind(window, "Ctrl+R", window._on_render)
    _bind(window, "Ctrl+Z", window._on_undo)
    _bind(window, "Ctrl+Shift+Z", window._on_redo)
    _bind(window, "Ctrl+Y", window._on_redo)
    _bind(window, "Space", window.preview_widget.toggle_play)
    _bind(window, "Left", window.preview_widget._step_back)
    _bind(window, "Right", window.preview_widget._step_forward)
    _bind(window, "F1", window._show_shortcuts)

    # Clip navigation
    _bind(window, "Ctrl+Up", lambda: _select_adjacent(window, -1))
    _bind(window, "Ctrl+Down", lambda: _select_adjacent(window, 1))


def _bind(window, key_str: str, callback) -> None:
    shortcut = QShortcut(QKeySequence(key_str), window)
    shortcut.activated.connect(callback)


def _select_adjacent(window, delta: int) -> None:
    project = window.project
    n = project.clip_model.rowCount()
    if n == 0:
        return
    new_row = max(0, min(project.selected_row + delta, n - 1))
    project.select_clip(new_row)
