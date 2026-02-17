"""Render progress dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

from gui.models.project import Project
from gui.workers.mosh_worker import MoshWorker


class RenderDialog(QDialog):
    """Asks for output path, runs the mosh, shows progress."""

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._worker: MoshWorker | None = None
        self.setWindowTitle("Render")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._info = QLabel("Choose an output file to render the moshed result.")
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.hide()
        layout.addWidget(self._progress)

        self._btn = QPushButton("Choose Output && Render")
        self._btn.setObjectName("accent")
        self._btn.clicked.connect(self._start)
        layout.addWidget(self._btn)

    def _start(self) -> None:
        if not self._project.has_timeline_items():
            self._info.setText("Timeline is empty.")
            return
        if not self._project.timeline_all_ready():
            self._info.setText("Some timeline clips are still normalizing. Please wait.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Moshed AVI", "", "AVI Files (*.avi);;All Files (*)"
        )
        if not path:
            return

        self._btn.setEnabled(False)
        self._progress.show()
        self._info.setText("Rendering...")

        self._worker = MoshWorker(self._project.timeline_render_clips(), Path(path), self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_done(self, out_path: str) -> None:
        self._progress.hide()
        self._info.setText(f"Saved: {out_path}")
        self._btn.setText("Close")
        self._btn.setEnabled(True)
        self._btn.clicked.disconnect()
        self._btn.clicked.connect(self.accept)

    def _on_error(self, msg: str) -> None:
        self._progress.hide()
        self._info.setText(f"Error: {msg}")
        self._btn.setEnabled(True)
