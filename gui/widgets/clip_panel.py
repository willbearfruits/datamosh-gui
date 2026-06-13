"""Left panel: clip list with thumbnails, drag-reorder, and import."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Optional

from PySide6.QtCore import QSize, Qt, QThread, QSettings, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from gui.dialogs.normalize_dialog import NormalizeDialog
from gui.models.clip_model import ClipProfile
from gui.models.project import Project
from gui.workers.iframe_inject_worker import IFrameInjectWorker
from gui.workers.normalize_worker import NormalizeWorker

VIDEO_FILTER = "Video Files (*.avi *.mp4 *.mkv *.mov *.webm *.flv *.wmv);;All Files (*)"
THUMB_SIZE = QSize(80, 45)
SETTINGS_PREFIX = "import/"

IMPORT_MODE_NORMALIZE = "normalize"
IMPORT_MODE_PREFER_SOURCE = "prefer_source"
DIRECT_IMPORT_CODECS = {"mpeg4"}


def default_import_settings() -> dict[str, Any]:
    return {
        "mode": IMPORT_MODE_NORMALIZE,
        "preset": "balanced",
        "width": None,
        "height": None,
        "qscale": None,
        "gop": None,
        "keep_audio": True,
        "remember_defaults": True,
    }


def normalize_import_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    out = default_import_settings()
    if raw:
        out.update(raw)

    mode = str(out.get("mode") or IMPORT_MODE_NORMALIZE)
    if mode not in {IMPORT_MODE_NORMALIZE, IMPORT_MODE_PREFER_SOURCE}:
        mode = IMPORT_MODE_NORMALIZE
    out["mode"] = mode

    preset = str(out.get("preset") or "balanced").lower()
    if preset not in {"fast", "balanced", "sharp"}:
        preset = "balanced"
    out["preset"] = preset

    out["width"] = _to_opt_int(out.get("width"), min_value=2)
    out["height"] = _to_opt_int(out.get("height"), min_value=2)
    out["qscale"] = _to_opt_int(out.get("qscale"), min_value=1)
    out["gop"] = _to_opt_int(out.get("gop"), min_value=1)
    out["keep_audio"] = _to_bool(out.get("keep_audio"), default=True)
    out["remember_defaults"] = _to_bool(out.get("remember_defaults"), default=True)
    return out


def _to_opt_int(value: object, *, min_value: int) -> Optional[int]:
    try:
        n = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return n if n >= min_value else None


def _to_bool(value: object, *, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


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


class VideoInfoWorker(QThread):
    """Probe video frame count, fps, and dimensions off the main thread."""

    done = Signal(int, int, float, int, int)  # row, total_frames, fps, width, height

    def __init__(self, path: Path, row: int, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._row = row

    def run(self) -> None:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-select_streams", "v:0",
                    "-count_packets",
                    "-show_entries", "stream=width,height,nb_read_packets,r_frame_rate",
                    "-of", "json",
                    str(self._path),
                ],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return
            data = json.loads(result.stdout)
            streams = data.get("streams", [])
            if not streams:
                return
            stream = streams[0]
            fps_str = str(stream.get("r_frame_rate", "30/1"))
            if "/" in fps_str:
                num, den = fps_str.split("/")
                fps = float(num) / float(den) if float(den) else 30.0
            else:
                fps = float(fps_str)
            total_frames = int(stream.get("nb_read_packets", 0))
            width = int(stream.get("width", 0) or 0)
            height = int(stream.get("height", 0) or 0)
            self.done.emit(self._row, total_frames, fps, width, height)
        except subprocess.TimeoutExpired:
            print(f"[warn] ffprobe timed out for {self._path}", flush=True)
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            print(f"[warn] ffprobe parse error for {self._path}: {exc}", flush=True)
        except FileNotFoundError:
            print("[warn] ffprobe not found on PATH", flush=True)


class CodecProbeWorker(QThread):
    """Probe a video's codec name off the UI thread for the direct-import check."""

    done = Signal(int, str)  # row, codec_name ("" on failure)

    def __init__(self, path: Path, row: int, parent=None) -> None:
        super().__init__(parent)
        self._path = path
        self._row = row

    def run(self) -> None:
        codec = ""
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_name",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(self._path),
                ],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                codec = (result.stdout.strip().splitlines() or [""])[0].strip().lower()
        except Exception:
            codec = ""
        self.done.emit(self._row, codec)


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
        self._settings = QSettings()
        self._build_ui()

    def _build_ui(self) -> None:
        self.setMinimumWidth(250)
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
        self._list_view.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self._list_view.clicked.connect(self._on_item_clicked)
        self._project.clip_selected.connect(self._on_clip_selected_externally)
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
        if not paths:
            return
        settings = self._prompt_import_settings()
        if not settings:
            return
        self.add_files(paths, import_settings=settings)

    def add_files(self, paths: list[str], import_settings: dict[str, Any] | None = None) -> None:
        settings = normalize_import_settings(import_settings or self._load_import_settings())
        for p in paths:
            path = Path(p)
            if not path.is_file():
                continue
            clip = ClipProfile(source_path=path)
            row = self._project.add_clip(clip)
            self._start_thumbnail(path, row)
            self._start_ingest(row, settings)

    # -- Project load support ----------------------------------------------

    def current_import_settings(self) -> dict[str, Any]:
        """The persisted import settings (used when saving a project)."""
        return self._load_import_settings()

    def reingest_loaded_clip(self, row: int, settings: dict[str, Any]) -> None:
        """Re-ingest a clip recreated from a loaded project so it becomes ready.

        Normal clips are re-normalized; injected I-frame clips are rebuilt from
        their source media via the inject worker.
        """
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            return
        if not clip.source_path.is_file():
            self._project.status_message.emit(
                f"Clip {row + 1}: source not found ({clip.source_path.name})"
            )
            return
        if clip.source_kind == "iframe":
            self._start_iframe_reingest(row, clip)
        else:
            self._start_thumbnail(clip.source_path, row)
            self._start_ingest(row, normalize_import_settings(settings))

    def _start_iframe_reingest(self, row: int, clip: ClipProfile) -> None:
        clip.normalizing = True
        self._project.clip_model.update_clip(row)
        worker = IFrameInjectWorker(
            source=clip.source_path,
            width=clip.frame_width or None,
            height=clip.frame_height or None,
            fps=clip.fps,
            parent=self,
        )
        worker.finished_ok.connect(
            lambda out_path, out_fps, r=row: self._on_iframe_reingested(r, out_path, out_fps)
        )
        worker.error.connect(lambda msg, r=row: self._on_reingest_error(r, msg))
        worker.finished.connect(worker.deleteLater)
        self._track_worker(worker)
        worker.start()

    def _on_iframe_reingested(self, row: int, out_path: str, out_fps: float) -> None:
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            return
        out = Path(out_path)
        clip.normalized_path = out
        clip.temp_dir = out.parent
        clip.normalizing = False
        if out_fps > 0:
            clip.fps = out_fps
        self._project.clip_model.update_clip(row)
        self._project.clips_changed.emit()
        self._project.status_message.emit(f"Clip {row + 1} ready (injected I-frame)")

    def _on_reingest_error(self, row: int, msg: str) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.normalizing = False
            self._project.clip_model.update_clip(row)
        self._project.status_message.emit(f"Error restoring clip {row + 1}: {msg}")

    # -- Internals ---------------------------------------------------------

    def _on_item_clicked(self, index) -> None:
        self._project.select_clip(index.row())

    def _on_clip_selected_externally(self, row: int) -> None:
        if row < 0:
            self._list_view.clearSelection()
            return
        idx = self._project.clip_model.index(row, 0)
        if self._list_view.currentIndex() != idx:
            self._list_view.setCurrentIndex(idx)

    def _remove_selected(self) -> None:
        idx = self._list_view.currentIndex()
        if idx.isValid():
            self._project.remove_clip(idx.row())

    def _start_thumbnail(self, path: Path, row: int) -> None:
        worker = ThumbnailExtractor(path, row, self)
        worker.done.connect(self._on_thumbnail_ready)
        worker.finished.connect(worker.deleteLater)
        self._track_worker(worker)
        worker.start()

    def _on_thumbnail_ready(self, row: int, pix: QPixmap) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.thumbnail = pix
            self._project.clip_model.update_clip(row)

    def _start_ingest(self, row: int, settings: dict[str, Any]) -> None:
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            return

        # Only "prefer source" mode can skip normalization, and only for AVI input.
        # Probe the codec on a worker thread (this used to block the UI thread for
        # up to 5s) and decide direct-vs-normalize once the result arrives.
        if (
            settings.get("mode") == IMPORT_MODE_PREFER_SOURCE
            and clip.source_path.suffix.lower() == ".avi"
        ):
            clip.normalizing = True
            self._project.clip_model.update_clip(row)
            self._start_codec_probe(row, clip.source_path, settings)
            return

        self._start_normalize(row, settings)

    def _start_codec_probe(self, row: int, path: Path, settings: dict[str, Any]) -> None:
        worker = CodecProbeWorker(path, row, self)
        worker.done.connect(lambda r, codec: self._on_codec_probed(r, codec, settings))
        worker.finished.connect(worker.deleteLater)
        self._track_worker(worker)
        worker.start()

    def _on_codec_probed(self, row: int, codec: str, settings: dict[str, Any]) -> None:
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            return
        if codec in DIRECT_IMPORT_CODECS:
            clip.normalized_path = clip.source_path
            clip.normalizing = False
            self._project.clip_model.update_clip(row)
            self._project.clips_changed.emit()
            self._project.status_message.emit(f"Clip {row + 1} ready (source AVI)")
            self._start_video_info(row, clip.source_path)
        else:
            self._project.status_message.emit(
                f"Clip {row + 1}: source not compatible for direct import, normalizing..."
            )
            self._start_normalize(row, settings)

    def _start_normalize(self, row: int, settings: dict[str, Any]) -> None:
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            return
        cfg = normalize_import_settings(settings)
        worker = NormalizeWorker(
            clip.source_path,
            row,
            self,
            preset=cfg["preset"],
            width=cfg["width"],
            height=cfg["height"],
            qscale=cfg["qscale"],
            gop=cfg["gop"],
            keep_audio=cfg["keep_audio"],
        )
        worker.progress.connect(self._on_normalize_progress)
        worker.finished_ok.connect(self._on_normalize_done)
        worker.error.connect(self._on_normalize_error)
        worker.finished.connect(worker.deleteLater)
        clip.normalizing = True
        self._project.clip_model.update_clip(row)
        self._track_worker(worker)
        worker.start()

    def _on_normalize_progress(self, row: int, pct: int) -> None:
        self._project.status_message.emit(f"Normalizing clip {row + 1}: {pct}%")

    def _on_normalize_done(self, row: int, path: str) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            out = Path(path)
            clip.normalized_path = out
            clip.temp_dir = out.parent
            clip.normalizing = False
            self._project.clip_model.update_clip(row)
            self._project.clips_changed.emit()
            self._project.status_message.emit(f"Clip {row + 1} ready")
            self._start_video_info(row, out)

    def _on_normalize_error(self, row: int, msg: str) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.normalizing = False
            self._project.clip_model.update_clip(row)
        self._project.status_message.emit(f"Error normalizing clip {row + 1}: {msg}")

    def _start_video_info(self, row: int, path: Path) -> None:
        worker = VideoInfoWorker(path, row, self)
        worker.done.connect(self._on_video_info_ready)
        worker.finished.connect(worker.deleteLater)
        self._track_worker(worker)
        worker.start()

    def _on_video_info_ready(self, row: int, total_frames: int, fps: float, width: int, height: int) -> None:
        clip = self._project.clip_model.clip_at(row)
        if clip:
            clip.total_frames = total_frames
            clip.fps = fps
            clip.frame_width = width
            clip.frame_height = height
            self._project.clip_model.update_clip(row)

    # -- Import settings ---------------------------------------------------

    def _prompt_import_settings(self) -> Optional[dict[str, Any]]:
        initial = self._load_import_settings()
        dialog = NormalizeDialog(self, initial=initial)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        settings = normalize_import_settings(dialog.get_settings())
        if settings.get("remember_defaults", True):
            self._save_import_settings(settings)
        return settings

    def _load_import_settings(self) -> dict[str, Any]:
        defaults = default_import_settings()
        raw: dict[str, Any] = {}
        for key, default in defaults.items():
            raw[key] = self._settings.value(f"{SETTINGS_PREFIX}{key}", default)
        return normalize_import_settings(raw)

    def _save_import_settings(self, settings: dict[str, Any]) -> None:
        cfg = normalize_import_settings(settings)
        for key, value in cfg.items():
            if key == "remember_defaults":
                continue
            if key in {"width", "height", "qscale", "gop"}:
                self._settings.setValue(f"{SETTINGS_PREFIX}{key}", int(value or 0))
            else:
                self._settings.setValue(f"{SETTINGS_PREFIX}{key}", value)
        self._settings.sync()

    def _track_worker(self, worker: QThread) -> None:
        self._workers.append(worker)
        worker.finished.connect(lambda w=worker: self._forget_worker(w))

    def _forget_worker(self, worker: QThread) -> None:
        if worker in self._workers:
            self._workers.remove(worker)

    def shutdown(self) -> None:
        """Stop ingest/thumbnail workers before app shutdown."""
        for worker in list(self._workers):
            if worker.isRunning():
                worker.requestInterruption()
                worker.quit()
                if not worker.wait(1000):
                    worker.terminate()
                    worker.wait(300)
        self._workers.clear()
