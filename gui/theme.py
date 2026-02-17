"""Dark theme palette and stylesheet for the datamosh GUI."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette


# Colour constants used throughout the application.
BG_DARK = QColor(30, 30, 30)
BG_MID = QColor(42, 42, 42)
BG_LIGHT = QColor(55, 55, 55)
TEXT = QColor(210, 210, 210)
TEXT_DIM = QColor(140, 140, 140)
ACCENT = QColor(0, 150, 255)
ACCENT_HOVER = QColor(30, 170, 255)
BORDER = QColor(65, 65, 65)
ERROR = QColor(220, 50, 50)
SUCCESS = QColor(50, 200, 80)
ORANGE = QColor(255, 165, 0)

# Timeline colours
KEYFRAME_BLUE = QColor(60, 130, 255)
PFRAME_GREEN = QColor(80, 180, 80)
DUPLICATE_ORANGE = QColor(255, 160, 40)
PLAYHEAD_RED = QColor(220, 40, 40)
DROP_RED = QColor(180, 40, 40, 120)


def make_dark_palette() -> QPalette:
    """Return a QPalette configured for a dark UI."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, BG_MID)
    p.setColor(QPalette.ColorRole.WindowText, TEXT)
    p.setColor(QPalette.ColorRole.Base, BG_DARK)
    p.setColor(QPalette.ColorRole.AlternateBase, BG_MID)
    p.setColor(QPalette.ColorRole.ToolTipBase, BG_LIGHT)
    p.setColor(QPalette.ColorRole.ToolTipText, TEXT)
    p.setColor(QPalette.ColorRole.Text, TEXT)
    p.setColor(QPalette.ColorRole.Button, BG_MID)
    p.setColor(QPalette.ColorRole.ButtonText, TEXT)
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.Link, ACCENT)
    p.setColor(QPalette.ColorRole.Highlight, ACCENT)
    p.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    p.setColor(QPalette.ColorRole.PlaceholderText, TEXT_DIM)

    # Disabled state
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, TEXT_DIM)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, TEXT_DIM)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, TEXT_DIM)
    return p


STYLESHEET = """
QMainWindow, QDialog {
    background-color: #2a2a2a;
}

QSplitter::handle {
    background-color: #414141;
}
QSplitter::handle:horizontal { width: 3px; }
QSplitter::handle:vertical   { height: 3px; }

QToolBar {
    background-color: #1e1e1e;
    border-bottom: 1px solid #414141;
    spacing: 4px;
    padding: 2px;
}
QToolBar QToolButton {
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 4px 8px;
    color: #d2d2d2;
}
QToolBar QToolButton:hover {
    background-color: #373737;
    border-color: #555;
}
QToolBar QToolButton:pressed {
    background-color: #0096ff;
}

QPushButton {
    background-color: #373737;
    border: 1px solid #555;
    border-radius: 4px;
    padding: 5px 14px;
    color: #d2d2d2;
    min-height: 22px;
}
QPushButton:hover { background-color: #444; }
QPushButton:pressed { background-color: #0096ff; }
QPushButton:disabled { color: #666; }
QPushButton#accent {
    background-color: #0096ff;
    border-color: #0096ff;
    color: white;
}
QPushButton#accent:hover { background-color: #1eaaff; }

QLabel { color: #d2d2d2; }

QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #1e1e1e;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 6px;
    color: #d2d2d2;
    min-height: 20px;
}
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #0096ff;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #555;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #0096ff;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}
QSlider::sub-page:horizontal {
    background: #0096ff;
    border-radius: 2px;
}

QScrollBar:vertical {
    background: #1e1e1e;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background: #555;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QListView {
    background-color: #1e1e1e;
    border: 1px solid #414141;
    border-radius: 4px;
    outline: none;
}
QListView::item {
    padding: 4px;
    border-bottom: 1px solid #333;
}
QListView::item:selected {
    background-color: #0096ff;
    color: white;
}
QListView::item:hover:!selected {
    background-color: #373737;
}

QStatusBar {
    background-color: #1e1e1e;
    border-top: 1px solid #414141;
    color: #8c8c8c;
}

QProgressBar {
    background-color: #1e1e1e;
    border: 1px solid #414141;
    border-radius: 3px;
    text-align: center;
    color: #d2d2d2;
    height: 16px;
}
QProgressBar::chunk {
    background-color: #0096ff;
    border-radius: 2px;
}

QGroupBox {
    border: 1px solid #414141;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 12px;
    color: #d2d2d2;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}

QCheckBox { color: #d2d2d2; spacing: 6px; }
QCheckBox::indicator {
    width: 16px; height: 16px;
    border: 1px solid #555;
    border-radius: 3px;
    background-color: #1e1e1e;
}
QCheckBox::indicator:checked {
    background-color: #0096ff;
    border-color: #0096ff;
}

QToolTip {
    background-color: #373737;
    color: #d2d2d2;
    border: 1px solid #555;
    padding: 4px;
}

QMenuBar {
    background-color: #1e1e1e;
    border-bottom: 1px solid #414141;
    color: #d2d2d2;
}
QMenuBar::item:selected { background-color: #373737; }
QMenu {
    background-color: #2a2a2a;
    border: 1px solid #414141;
    color: #d2d2d2;
}
QMenu::item:selected { background-color: #0096ff; }
QMenu::separator { height: 1px; background: #414141; margin: 4px 8px; }
"""
