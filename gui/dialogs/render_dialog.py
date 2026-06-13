"""Render progress dialog."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
)

# label, extension, file-dialog filter
EXPORT_FORMATS = [
    ("AVI — Xvid (native, fastest)", "avi", "AVI Files (*.avi)"),
    ("MP4 — H.264 (shareable)", "mp4", "MP4 Files (*.mp4)"),
    ("MOV — H.264", "mov", "MOV Files (*.mov)"),
]

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

        fmt_row = QHBoxLayout()
        fmt_row.addWidget(QLabel("Format:"))
        self._format = QComboBox()
        for label, ext, _filter in EXPORT_FORMATS:
            self._format.addItem(label, ext)
        fmt_row.addWidget(self._format, 1)
        layout.addLayout(fmt_row)

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

        ext = self._format.currentData()
        flt = next((f for _l, e, f in EXPORT_FORMATS if e == ext), "All Files (*)")
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Moshed Video", "", f"{flt};;All Files (*)"
        )
        if not path:
            return
        out = Path(path)
        if out.suffix.lower() != f".{ext}":
            out = out.with_suffix(f".{ext}")

        self._btn.setEnabled(False)
        self._progress.show()
        self._info.setText("Rendering (transcoding to MP4/MOV may take a little longer)..."
                           if ext != "avi" else "Rendering...")

        self._worker = MoshWorker(self._project.timeline_render_clips(), out, self)
        self._worker.finished_ok.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._worker.deleteLater)
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
        self._info.setText(f"Error: {msg}\n\nClick 'Choose Output & Render' to try again.")
        self._btn.setEnabled(True)

    def closeEvent(self, event) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.finished_ok.disconnect()
            self._worker.error.disconnect()
            if not self._worker.wait(2000):
                self._worker.terminate()
                self._worker.wait(300)
        super().closeEvent(event)
