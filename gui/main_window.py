"""Main window with splitter-based layout."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QAction, QCloseEvent, QDesktopServices, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui.models import project_io

from gui.widgets.clip_panel import ClipPanel
from gui.widgets.preview_widget import PreviewWidget
from gui.widgets.settings_panel import SettingsPanel
from gui.widgets.timeline_widget import TimelineWidget
from gui.widgets.toolbar import Toolbar
from gui.models.project import Project
from gui.version import (
    BUY_ME_A_COFFEE_URL,
    PATREON_URL,
    REPOSITORY,
    REPOSITORY_URL,
    get_version,
    release_channel,
)
from gui.workers.update_worker import UpdateWorker


class MainWindow(QMainWindow):
    """Top-level window containing all panels arranged with QSplitters."""

    files_dropped = Signal(list)  # list[str] paths

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"Datamosh {get_version()}")
        self.setMinimumSize(1000, 650)
        self.resize(1280, 800)

        self.project = Project()
        self._update_worker: UpdateWorker | None = None
        self._project_path: Optional[Path] = None
        self._dirty = False
        self._loading = False

        self._build_ui()
        self._connect_signals()
        self.setAcceptDrops(True)
        self._update_title()

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
        self._build_menus()

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
        self.clip_panel.setMinimumWidth(250)
        self.settings_panel.setMinimumWidth(320)
        h_splitter.addWidget(self.clip_panel)
        h_splitter.addWidget(centre)
        h_splitter.addWidget(self.settings_panel)
        h_splitter.setStretchFactor(0, 1)
        h_splitter.setStretchFactor(1, 4)
        h_splitter.setStretchFactor(2, 1)
        h_splitter.setSizes([280, 720, 360])

        self.setCentralWidget(h_splitter)

        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")

    def _build_menus(self) -> None:
        menu = self.menuBar()

        file_menu = menu.addMenu("&File")

        self._new_action = QAction("New Project", self)
        self._new_action.setShortcut(QKeySequence.StandardKey.New)
        self._new_action.triggered.connect(self._new_project)
        file_menu.addAction(self._new_action)

        self._open_project_action = QAction("Open Project...", self)
        self._open_project_action.setShortcut(QKeySequence("Ctrl+Shift+P"))
        self._open_project_action.triggered.connect(self._open_project)
        file_menu.addAction(self._open_project_action)

        self._save_action = QAction("Save Project", self)
        self._save_action.setShortcut(QKeySequence.StandardKey.Save)
        self._save_action.triggered.connect(self._save_project)
        file_menu.addAction(self._save_action)

        self._save_as_action = QAction("Save Project As...", self)
        self._save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        self._save_as_action.triggered.connect(self._save_project_as)
        file_menu.addAction(self._save_as_action)

        file_menu.addSeparator()
        file_menu.addAction(self.toolbar.open_action)
        file_menu.addAction(self.toolbar.add_action)
        file_menu.addSeparator()
        file_menu.addAction(self.toolbar.render_action)
        file_menu.addSeparator()
        self._quit_action = QAction("Quit", self)
        self._quit_action.setShortcut(QKeySequence.StandardKey.Quit)
        self._quit_action.triggered.connect(self.close)
        file_menu.addAction(self._quit_action)

        edit_menu = menu.addMenu("&Edit")
        edit_menu.addAction(self.toolbar.undo_action)
        edit_menu.addAction(self.toolbar.redo_action)

        timeline_menu = menu.addMenu("&Timeline")
        self._menu_cut = timeline_menu.addAction("Cut At Playhead")
        self._menu_cut.triggered.connect(self.timeline_widget.cut_at_playhead)
        self._menu_inject = timeline_menu.addAction("Inject I-Frame From Media...")
        self._menu_inject.triggered.connect(self.timeline_widget.inject_iframe_from_media)
        self._menu_drop = timeline_menu.addAction("Toggle Drop First I-Frame")
        self._menu_drop.triggered.connect(self.timeline_widget.toggle_drop_first_selected)
        self._menu_delete = timeline_menu.addAction("Delete Selected Segment")
        self._menu_delete.triggered.connect(self.timeline_widget.delete_selected)

        help_menu = menu.addMenu("&Help")
        self._menu_repo = help_menu.addAction("GitHub Repository")
        self._menu_repo.triggered.connect(lambda: self._open_url(REPOSITORY_URL))
        self._menu_patreon = help_menu.addAction("Patreon")
        self._menu_patreon.triggered.connect(lambda: self._open_url(PATREON_URL))
        self._menu_bmc = help_menu.addAction("Buy Me a Coffee")
        self._menu_bmc.triggered.connect(lambda: self._open_url(BUY_ME_A_COFFEE_URL))
        help_menu.addSeparator()
        help_menu.addAction(self.toolbar.update_action)
        help_menu.addSeparator()
        help_menu.addAction(self.toolbar.help_action)

    # -- Signal wiring -----------------------------------------------------

    def _connect_signals(self) -> None:
        self.toolbar.open_clicked.connect(self.clip_panel.open_files)
        self.toolbar.add_clip_clicked.connect(self.clip_panel.open_files)
        self.toolbar.render_clicked.connect(self._on_render)
        self.toolbar.undo_clicked.connect(self._on_undo)
        self.toolbar.redo_clicked.connect(self._on_redo)
        self.toolbar.update_clicked.connect(self._check_updates)
        self.toolbar.help_clicked.connect(self._show_shortcuts)
        self.files_dropped.connect(self.clip_panel.add_files)

        self.project.clip_selected.connect(self.settings_panel.load_clip)
        self.project.clip_selected.connect(self.preview_widget.on_clip_selected)
        self.project.clips_changed.connect(self.preview_widget.schedule_update)
        self.project.clips_changed.connect(self.timeline_widget.refresh)
        self.project.timeline_changed.connect(self.preview_widget.schedule_update)
        self.project.timeline_changed.connect(self.timeline_widget.refresh)
        self.project.timeline_item_selected.connect(self.preview_widget.schedule_update)
        self.project.history_changed.connect(self._set_history_state)
        self.project.timeline_item_selected.connect(self._set_timeline_menu_state)
        self.project.clips_changed.connect(self._set_timeline_menu_state)
        self.project.timeline_changed.connect(self._set_timeline_menu_state)
        self.timeline_widget.inject_state_changed.connect(self._set_timeline_menu_state)

        # Timeline clip selection (clicking a clip region in the timeline)
        self.timeline_widget.clip_clicked.connect(self.project.select_clip)

        # Bidirectional timeline <-> preview link
        self.timeline_widget.frame_changed.connect(self.preview_widget.show_frame)
        self.preview_widget.frame_changed.connect(self.timeline_widget.set_playhead)

        # Status bar
        self.project.status_message.connect(self.set_status)
        self._set_history_state(self.project.can_undo(), self.project.can_redo())
        self._set_timeline_menu_state()

        # Unsaved-changes tracking. rowsInserted/rowsRemoved fire on add/remove
        # (not on normalize-completion, which only updates row data), so a loaded
        # project stays clean until the user actually edits it.
        self.project.clip_updated.connect(self._mark_dirty)
        self.project.timeline_changed.connect(self._mark_dirty)
        self.project.clip_model.rowsInserted.connect(self._mark_dirty)
        self.project.clip_model.rowsRemoved.connect(self._mark_dirty)

    # -- Drag-and-drop -----------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)

    def closeEvent(self, event: QCloseEvent) -> None:
        if not self._maybe_discard_changes():
            event.ignore()
            return
        try:
            self.preview_widget.shutdown()
            self.timeline_widget.shutdown()
            self.clip_panel.shutdown()
            self.project.cleanup_all()
            if self._update_worker and self._update_worker.isRunning():
                self._update_worker.quit()
                if not self._update_worker.wait(1000):
                    self._update_worker.terminate()
                    self._update_worker.wait(300)
        finally:
            super().closeEvent(event)

    # -- Project persistence ----------------------------------------------

    def _mark_dirty(self, *_args) -> None:
        if self._loading or self._dirty:
            return
        self._dirty = True
        self._update_title()

    def _set_clean(self) -> None:
        self._dirty = False
        self._update_title()

    def _update_title(self) -> None:
        name = self._project_path.name if self._project_path else "Untitled"
        star = "*" if self._dirty else ""
        self.setWindowTitle(f"Datamosh {get_version()} — {name}{star}")

    def _maybe_discard_changes(self) -> bool:
        """Prompt to save/discard if dirty. Return True to proceed, False to cancel."""
        if not self._dirty:
            return True
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Warning)
        box.setWindowTitle("Unsaved Changes")
        box.setText("This project has unsaved changes.")
        box.setInformativeText("Save them before continuing?")
        save_btn = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Discard", QMessageBox.ButtonRole.DestructiveRole)
        cancel_btn = box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked == cancel_btn:
            return False
        if clicked == save_btn:
            return self._save_project()
        return True  # discard

    def _new_project(self) -> None:
        if not self._maybe_discard_changes():
            return
        self._loading = True
        try:
            self.clip_panel.cancel_ingest()
            self.preview_widget.reset()
            self.project.clear()
        finally:
            self._loading = False
        self._project_path = None
        self._set_clean()
        self.set_status("New project", 1500)

    def _open_project(self) -> None:
        if not self._maybe_discard_changes():
            return
        start_dir = str(self._project_path.parent) if self._project_path else ""
        path_str, _ = QFileDialog.getOpenFileName(
            self, "Open Project", start_dir,
            f"Datamosh Project (*{project_io.PROJECT_SUFFIX});;All Files (*)",
        )
        if path_str:
            self._load_project_file(Path(path_str))

    def _load_project_file(self, path: Path) -> None:
        try:
            data = project_io.read_project(path)
        except project_io.ProjectLoadError as exc:
            QMessageBox.critical(self, "Open Project", str(exc))
            return

        self._loading = True
        try:
            self.clip_panel.cancel_ingest()
            self.preview_widget.reset()
            settings = data.get("import_settings") or self.clip_panel.current_import_settings()
            clips = self.project.install_loaded_state(data)
            for row in range(len(clips)):
                self.clip_panel.reingest_loaded_clip(row, settings)
        finally:
            self._loading = False

        self._project_path = path
        self._set_clean()
        missing = sum(1 for c in self.project.clips if not c.source_path.is_file())
        if missing:
            QMessageBox.warning(
                self, "Open Project",
                f"{missing} source file(s) could not be found. "
                "Those clips will stay empty until their sources are available.",
            )
        self.set_status(f"Opened {path.name}", 2500)

    def _save_project(self) -> bool:
        if self._project_path is None:
            return self._save_project_as()
        return self._do_save_to(self._project_path)

    def _save_project_as(self) -> bool:
        start = str(self._project_path) if self._project_path else f"untitled{project_io.PROJECT_SUFFIX}"
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", start,
            f"Datamosh Project (*{project_io.PROJECT_SUFFIX});;All Files (*)",
        )
        if not path_str:
            return False
        path = Path(path_str)
        if path.suffix.lower() != project_io.PROJECT_SUFFIX:
            path = path.with_suffix(project_io.PROJECT_SUFFIX)
        return self._do_save_to(path)

    def _do_save_to(self, path: Path) -> bool:
        try:
            project_io.write_project(
                path, self.project, self.clip_panel.current_import_settings(), get_version()
            )
        except OSError as exc:
            QMessageBox.critical(self, "Save Project", f"Could not save project:\n{exc}")
            return False
        self._project_path = path
        self._set_clean()
        self.set_status(f"Saved {path.name}", 2500)
        return True

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

    def _check_updates(self) -> None:
        if self._update_worker and self._update_worker.isRunning():
            self.set_status("Update check already in progress...", 1500)
            return

        self.set_status("Checking for updates...")
        self._update_worker = UpdateWorker(
            current_version=get_version(),
            repository=REPOSITORY,
            channel=release_channel(),
            parent=self,
        )
        self._update_worker.finished_ok.connect(self._on_update_result)
        self._update_worker.finished.connect(self._update_worker.deleteLater)
        self._update_worker.start()

    def _on_update_result(self, result) -> None:
        self._update_worker = None

        if result.error:
            self.set_status("Update check failed", 2000)
            QMessageBox.warning(self, "Update Check", f"Could not check updates:\n{result.error}")
            return

        if not result.has_update:
            self.set_status("You are on the latest version", 2000)
            QMessageBox.information(
                self,
                "Update Check",
                f"No updates available.\nCurrent version: {result.current_version}",
            )
            return

        latest = result.latest
        if latest is None:
            return

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("Update Available")
        box.setText(f"A new version is available: {latest.version}")
        box.setInformativeText(
            f"Current: {result.current_version}\n"
            f"Latest: {latest.version}\n\n"
            "Open the download page now?"
        )
        open_btn = box.addButton("Open Download", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Later", QMessageBox.ButtonRole.RejectRole)
        box.exec()

        if box.clickedButton() == open_btn:
            QDesktopServices.openUrl(QUrl(latest.download_url))

    def set_status(self, msg: str, timeout: int = 0) -> None:
        self.status_bar.showMessage(msg, timeout)

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _set_history_state(self, can_undo: bool, can_redo: bool) -> None:
        self.toolbar.set_history_state(can_undo, can_redo)

    def _set_timeline_menu_state(self, *_args) -> None:
        has_items = self.project.has_timeline_items()
        has_selection = self.project.selected_timeline_index >= 0
        self._menu_cut.setEnabled(has_items)
        self._menu_drop.setEnabled(has_selection)
        self._menu_delete.setEnabled(has_selection)
        self._menu_inject.setEnabled(not self.timeline_widget.inject_running())
