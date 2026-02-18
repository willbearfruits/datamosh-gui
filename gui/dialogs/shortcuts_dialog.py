"""Keyboard shortcut help dialog."""

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QPushButton,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
)

from gui.version import BUY_ME_A_COFFEE_URL, PATREON_URL, REPOSITORY_URL


SHORTCUTS_TEXT = """
<table cellspacing="8">
<tr><td><b>Ctrl+O</b></td><td>Open video file(s)</td></tr>
<tr><td><b>Ctrl+Shift+O</b></td><td>Add clip(s)</td></tr>
<tr><td><b>Ctrl+R</b></td><td>Render moshed output</td></tr>
<tr><td><b>Ctrl+Z</b></td><td>Undo</td></tr>
<tr><td><b>Ctrl+Shift+Z / Ctrl+Y</b></td><td>Redo</td></tr>
<tr><td><b>Space</b></td><td>Play / Pause preview</td></tr>
<tr><td><b>Left / Right</b></td><td>Step frame backward / forward</td></tr>
<tr><td><b>Ctrl+Up / Down</b></td><td>Select previous / next clip</td></tr>
<tr><td><b>Ctrl+K</b></td><td>Cut selected timeline segment at playhead</td></tr>
<tr><td><b>Ctrl+Shift+I</b></td><td>Inject single I-frame clip from media</td></tr>
<tr><td><b>I</b></td><td>Toggle drop first I-frame for selected segment</td></tr>
<tr><td><b>Delete</b></td><td>Delete selected timeline segment</td></tr>
<tr><td><b>F1</b></td><td>Show this help</td></tr>
<tr><td><b>Ctrl+wheel</b></td><td>Zoom timeline</td></tr>
<tr><td><b>Wheel</b></td><td>Scroll timeline</td></tr>
</table>
"""


class ShortcutsDialog(QDialog):
    """Simple dialog listing keyboard shortcuts."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard Shortcuts")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        title = QLabel("Datamosh Keyboard Shortcuts")
        title.setStyleSheet("font-size: 15px; font-weight: bold; padding-bottom: 8px;")
        layout.addWidget(title)

        body = QLabel(SHORTCUTS_TEXT)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setWordWrap(True)
        layout.addWidget(body)

        links = QHBoxLayout()
        btn_repo = QPushButton("GitHub")
        btn_repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPOSITORY_URL)))
        links.addWidget(btn_repo)

        btn_patreon = QPushButton("Patreon")
        btn_patreon.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(PATREON_URL)))
        links.addWidget(btn_patreon)

        btn_bmc = QPushButton("Buy Me a Coffee")
        btn_bmc.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(BUY_ME_A_COFFEE_URL)))
        links.addWidget(btn_bmc)
        links.addStretch()
        layout.addLayout(links)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
