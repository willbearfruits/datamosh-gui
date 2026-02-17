"""Top toolbar with action buttons."""

from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QToolBar


class Toolbar(QToolBar):
    open_clicked = Signal()
    add_clip_clicked = Signal()
    render_clicked = Signal()
    undo_clicked = Signal()
    redo_clicked = Signal()
    update_clicked = Signal()
    help_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__("Main Toolbar", parent)
        self.setMovable(False)

        self._open = QAction("Open", self)
        self._open.setToolTip("Open video file(s)  (Ctrl+O)")
        self._open.triggered.connect(self.open_clicked)
        self.addAction(self._open)

        self._add = QAction("Add Clip", self)
        self._add.setToolTip("Add another clip  (Ctrl+Shift+O)")
        self._add.triggered.connect(self.add_clip_clicked)
        self.addAction(self._add)

        self.addSeparator()

        self._render = QAction("Render", self)
        self._render.setToolTip("Render moshed output  (Ctrl+R)")
        self._render.triggered.connect(self.render_clicked)
        self.addAction(self._render)

        self.addSeparator()

        self._undo = QAction("Undo", self)
        self._undo.setToolTip("Undo timeline/settings change  (Ctrl+Z)")
        self._undo.setEnabled(False)
        self._undo.triggered.connect(self.undo_clicked)
        self.addAction(self._undo)

        self._redo = QAction("Redo", self)
        self._redo.setToolTip("Redo timeline/settings change  (Ctrl+Shift+Z)")
        self._redo.setEnabled(False)
        self._redo.triggered.connect(self.redo_clicked)
        self.addAction(self._redo)

        self.addSeparator()

        self._update = QAction("Update", self)
        self._update.setToolTip("Check for app updates")
        self._update.triggered.connect(self.update_clicked)
        self.addAction(self._update)

        self.addSeparator()

        self._help = QAction("Help", self)
        self._help.setToolTip("Keyboard shortcuts  (F1)")
        self._help.triggered.connect(self.help_clicked)
        self.addAction(self._help)

    def set_history_state(self, can_undo: bool, can_redo: bool) -> None:
        self._undo.setEnabled(can_undo)
        self._redo.setEnabled(can_redo)
