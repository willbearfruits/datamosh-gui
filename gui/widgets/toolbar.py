"""Top toolbar with action buttons."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QStyle, QToolBar


def _tip(text: str, action: QAction) -> str:
    """Append the action's shortcut in platform-native form (e.g. ⌘O on macOS,
    Ctrl+O on Windows/Linux) so tooltips never show the wrong modifier."""
    seq = action.shortcut().toString(QKeySequence.SequenceFormat.NativeText)
    return f"{text}  ({seq})" if seq else text


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
        self.setIconSize(QSize(18, 18))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        style = self.style()

        self._open = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), "Open", self)
        self._open.setShortcut(QKeySequence("Ctrl+O"))
        self._open.setToolTip(_tip("Open video file(s)", self._open))
        self._open.triggered.connect(self.open_clicked)
        self.addAction(self._open)

        self._add = QAction(style.standardIcon(QStyle.StandardPixmap.SP_FileIcon), "Add Clip", self)
        self._add.setShortcut(QKeySequence("Ctrl+Shift+O"))
        self._add.setToolTip(_tip("Add another clip", self._add))
        self._add.triggered.connect(self.add_clip_clicked)
        self.addAction(self._add)

        self.addSeparator()

        self._render = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton), "Render", self)
        self._render.setShortcut(QKeySequence("Ctrl+R"))
        self._render.setToolTip(_tip("Render moshed output", self._render))
        self._render.triggered.connect(self.render_clicked)
        self.addAction(self._render)

        self.addSeparator()

        self._undo = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack), "Undo", self)
        self._undo.setShortcut(QKeySequence.StandardKey.Undo)
        self._undo.setToolTip(_tip("Undo timeline/settings change", self._undo))
        self._undo.setEnabled(False)
        self._undo.triggered.connect(self.undo_clicked)
        self.addAction(self._undo)

        self._redo = QAction(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward), "Redo", self)
        self._redo.setShortcut(QKeySequence.StandardKey.Redo)
        self._redo.setToolTip(_tip("Redo timeline/settings change", self._redo))
        self._redo.setEnabled(False)
        self._redo.triggered.connect(self.redo_clicked)
        self.addAction(self._redo)

        self.addSeparator()

        self._update = QAction(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload), "Update", self)
        self._update.setToolTip("Check for app updates")
        self._update.triggered.connect(self.update_clicked)
        self.addAction(self._update)

        self.addSeparator()

        self._help = QAction(style.standardIcon(QStyle.StandardPixmap.SP_DialogHelpButton), "Help", self)
        self._help.setShortcut(QKeySequence("F1"))
        self._help.setToolTip(_tip("Keyboard shortcuts", self._help))
        self._help.triggered.connect(self.help_clicked)
        self.addAction(self._help)

    def set_history_state(self, can_undo: bool, can_redo: bool) -> None:
        self._undo.setEnabled(can_undo)
        self._redo.setEnabled(can_redo)

    @property
    def open_action(self) -> QAction:
        return self._open

    @property
    def add_action(self) -> QAction:
        return self._add

    @property
    def render_action(self) -> QAction:
        return self._render

    @property
    def undo_action(self) -> QAction:
        return self._undo

    @property
    def redo_action(self) -> QAction:
        return self._redo

    @property
    def update_action(self) -> QAction:
        return self._update

    @property
    def help_action(self) -> QAction:
        return self._help
