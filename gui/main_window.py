"""Main window with splitter-based layout."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QMainWindow,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.clip_panel import ClipPanel
from gui.widgets.preview_widget import PreviewWidget
from gui.widgets.settings_panel import SettingsPanel
from gui.widgets.timeline_widget import TimelineWidget
from gui.widgets.toolbar import Toolbar
from gui.models.project import Project


class MainWindow(QMainWindow):
    """Top-level window containing all panels arranged with QSplitters."""

    files_dropped = Signal(list)  # list[str] paths

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Datamosh")
        self.setMinimumSize(1000, 650)
        self.resize(1280, 800)

        self.project = Project()

        self._build_ui()
        self._connect_signals()
        self.setAcceptDrops(True)

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        # Toolbar
        self.toolbar = Toolbar()
        self.addToolBar(self.toolbar)

        # Panels
        self.clip_panel = ClipPanel(self.project)
        self.preview_widget = PreviewWidget(self.project)
        self.settings_panel = SettingsPanel(self.project)
        self.timeline_widget = TimelineWidget(self.project)

        # Centre column: preview on top, timeline on bottom
        centre = QWidget()
        centre_layout = QVBoxLayout(centre)
        centre_layout.setContentsMargins(0, 0, 0, 0)
        centre_layout.setSpacing(0)

        self._centre_splitter = QSplitter(Qt.Orientation.Vertical)
        self._centre_splitter.addWidget(self.preview_widget)
        self._centre_splitter.addWidget(self.timeline_widget)
        self._centre_splitter.setStretchFactor(0, 3)
        self._centre_splitter.setStretchFactor(1, 2)
        self._centre_splitter.setSizes([400, 250])
        # Wider handle so it's easy to grab
        self._centre_splitter.setHandleWidth(6)
        self._centre_splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background: qlineargradient(y1:0, y2:1,
                    stop:0 #333, stop:0.4 #555, stop:0.6 #555, stop:1 #333);
                height: 6px;
                border-radius: 3px;
                margin: 0 40px;
            }
        """)
        centre_layout.addWidget(self._centre_splitter)

        # Horizontal splitter: clip_panel | centre | settings
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.addWidget(self.clip_panel)
        h_splitter.addWidget(centre)
        h_splitter.addWidget(self.settings_panel)
        h_splitter.setStretchFactor(0, 1)
        h_splitter.setStretchFactor(1, 4)
        h_splitter.setStretchFactor(2, 1)
        h_splitter.setSizes([200, 680, 220])

        self.setCentralWidget(h_splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    # -- Signal wiring -----------------------------------------------------

    def _connect_signals(self) -> None:
        self.toolbar.open_clicked.connect(self.clip_panel.open_files)
        self.toolbar.add_clip_clicked.connect(self.clip_panel.open_files)
        self.toolbar.render_clicked.connect(self._on_render)
        self.toolbar.undo_clicked.connect(self._on_undo)
        self.toolbar.redo_clicked.connect(self._on_redo)
        self.toolbar.help_clicked.connect(self._show_shortcuts)
        self.files_dropped.connect(self.clip_panel.add_files)

        self.project.clip_selected.connect(self.settings_panel.load_clip)
        self.project.clip_selected.connect(self.preview_widget.on_clip_selected)
        self.project.clips_changed.connect(self.preview_widget.schedule_update)
        self.project.clips_changed.connect(self.timeline_widget.refresh)
        self.project.timeline_changed.connect(self.preview_widget.schedule_update)
        self.project.timeline_changed.connect(self.timeline_widget.refresh)
        self.project.timeline_item_selected.connect(self.preview_widget.schedule_update)
        self.project.history_changed.connect(self.toolbar.set_history_state)

        # Timeline clip selection (clicking a clip region in the timeline)
        self.timeline_widget.clip_clicked.connect(self.project.select_clip)

        # Bidirectional timeline <-> preview link
        self.timeline_widget.frame_changed.connect(self.preview_widget.show_frame)
        self.preview_widget.frame_changed.connect(self.timeline_widget.set_playhead)

        # Status bar
        self.project.status_message.connect(self.set_status)
        self.toolbar.set_history_state(self.project.can_undo(), self.project.can_redo())

    # -- Drag-and-drop -----------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)

    # -- Actions -----------------------------------------------------------

    def _on_render(self) -> None:
        from gui.dialogs.render_dialog import RenderDialog
        dlg = RenderDialog(self.project, parent=self)
        dlg.exec()

    def _show_shortcuts(self) -> None:
        from gui.dialogs.shortcuts_dialog import ShortcutsDialog
        dlg = ShortcutsDialog(parent=self)
        dlg.exec()

    def _on_undo(self) -> None:
        if self.project.undo():
            self.set_status("Undo", 1500)

    def _on_redo(self) -> None:
        if self.project.redo():
            self.set_status("Redo", 1500)

    def set_status(self, msg: str, timeout: int = 0) -> None:
        self.status_bar.showMessage(msg, timeout)
