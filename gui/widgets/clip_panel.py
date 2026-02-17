"""Left panel: clip list with thumbnails, drag-reorder, and import."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from gui.models.clip_model import ClipProfile
from gui.models.project import Project
from gui.workers.normalize_worker import NormalizeWorker

VIDEO_FILTER = "Video Files (*.avi *.mp4 *.mkv *.mov *.webm *.flv *.wmv);;All Files (*)"
THUMB_SIZE = QSize(80, 45)


class ThumbnailExtractor(QThread):
    """Extract a single thumbnail from a video file."""

    done = Signal(int, QPixmap)  # row, pixmap

    def __init__(self, path: Path, row: int, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._row = row

    def run(self) -> None:
        pix = _extract_thumbnail(self._path)
        if pix:
            self.done.emit(self._row, pix)


def _extract_thumbnail(path: Path) -> Optional[QPixmap]:
    """Try to grab a frame via ffmpeg, return scaled QPixmap or None."""
    try:
        proc = subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(path),
                "-vf", f"scale={THUMB_SIZE.width()}:{THUMB_SIZE.height()}:force_original_aspect_ratio=decrease",
                "-frames:v", "1", "-f", "image2pipe", "-vcodec", "bmp", "-"
            ],
            capture_output=True, timeout=10,
        )
        if proc.returncode == 0 and proc.stdout:
            img = QImage()
            img.loadFromData(proc.stdout, "BMP")
            if not img.isNull():
                return QPixmap.fromImage(img).scaled(
                    THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
    except Exception:
        pass
    return None


class ClipDelegate(QStyledItemDelegate):
    """Custom delegate that shows thumbnail + label."""

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), max(THUMB_SIZE.height() + 8, 52))


class ClipPanel(QWidget):
    """Panel showing the list of clips with drag-reorder."""

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._workers: list[QThread] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QLabel("Clips")
        header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        layout.addWidget(header)

        self._list_view = QListView()
        self._list_view.setModel(self._project.clip_model)
        self._list_view.setItemDelegate(ClipDelegate(self))
        self._list_view.setDragEnabled(True)
        self._list_view.setAcceptDrops(True)
        self._list_view.setDropIndicatorShown(True)
        self._list_view.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self._list_view.setDefaultDropAction(Qt.DropAction.MoveAction)
        self._list_view.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._list_view.clicked.connect(self._on_item_clicked)
        layout.addWidget(self._list_view, 1)

        btn_row = QHBoxLayout()
        self._btn_remove = QPushButton("Remove")
        self._btn_remove.clicked.connect(self._remove_selected)
        btn_row.addWidget(self._btn_remove)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    # -- Public slots ------------------------------------------------------

    def open_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Open Video", "", VIDEO_FILTER)
        if paths:
            self.add_files(paths)

    def add_files(self, paths: list[str]) -> None:
        for p in paths:
            path = Path(p)
            if not path.is_file():
                continue
            clip = ClipProfile(source_path=path)
            row = self._project.add_clip(clip)
            self._start_thumbnail(path, row)
            self._start_normalize(row)

    # -- Internals ---------------------------------------------------------

    def _on_item_clicked(self, index) -> None:
        self._project.select_clip(index.row())

    def _remove_selected(self) -> None:
        idx = self._list_view.currentIndex()
        if idx.isValid():
            self._project.remove_clip(idx.row())

    def _start_thumbnail(self, path: Path, row: int) -> None:
        worker = ThumbnailExtractor(path, row, self)
        worker.done.connect(self._on_thumbnail_ready)
        worker.finished.connect(worker.deleteLater)
        self._workers.append(worker)
        worker.start()

    def _on_thumbnail_ready(self, row: int, pix: QPixmap) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.thumbnail = pix
            self._project.clip_model.update_clip(row)

    def _start_normalize(self, row: int) -> None:
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            return
        worker = NormalizeWorker(clip.source_path, row, self)
        worker.progress.connect(self._on_normalize_progress)
        worker.finished_ok.connect(self._on_normalize_done)
        worker.error.connect(self._on_normalize_error)
        worker.finished.connect(worker.deleteLater)
        clip.normalizing = True
        self._project.clip_model.update_clip(row)
        self._workers.append(worker)
        worker.start()

    def _on_normalize_progress(self, row: int, pct: int) -> None:
        self._project.status_message.emit(f"Normalizing clip {row + 1}: {pct}%")

    def _on_normalize_done(self, row: int, path: str) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.normalized_path = Path(path)
            clip.normalizing = False
            self._project.clip_model.update_clip(row)
            self._project.clips_changed.emit()
            self._project.status_message.emit(f"Clip {row + 1} ready")
            # Probe frame count and fps
            self._probe_video_info(clip)

    def _on_normalize_error(self, row: int, msg: str) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.normalizing = False
            self._project.clip_model.update_clip(row)
        self._project.status_message.emit(f"Error normalizing clip {row + 1}: {msg}")

    def _probe_video_info(self, clip: ClipProfile) -> None:
        """Probe frame count and fps from the normalized file."""
        if not clip.normalized_path:
            return
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-select_streams", "v:0",
                    "-count_packets",
                    "-show_entries", "stream=nb_read_packets,r_frame_rate",
                    "-of", "csv=p=0",
                    str(clip.normalized_path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(",")
                if len(parts) >= 2:
                    fps_str = parts[0]
                    if "/" in fps_str:
                        num, den = fps_str.split("/")
                        clip.fps = float(num) / float(den)
                    else:
                        clip.fps = float(fps_str)
                    clip.total_frames = int(parts[1])
        except Exception:
            pass
