"""Tests for toolbar tooltip shortcut rendering (macOS shows native modifiers)."""

import pytest
from PySide6.QtGui import QAction, QKeySequence

from gui.widgets.toolbar import _tip


@pytest.fixture(autouse=True)
def _app(qtbot):
    # qtbot ensures a QApplication for QAction/QKeySequence.
    return qtbot


def test_tip_appends_native_shortcut():
    action = QAction("x")
    action.setShortcut(QKeySequence("Ctrl+K"))
    tip = _tip("Cut", action)
    assert tip.startswith("Cut  (") and tip.endswith(")")
    # Whatever the platform native form is, the literal portable "Ctrl+K" appears
    # on Win/Linux; on macOS it renders with the ⌘ glyph. Either way it's appended.


def test_tip_omits_parens_without_shortcut():
    action = QAction("y")  # no shortcut
    assert _tip("Check for app updates", action) == "Check for app updates"
