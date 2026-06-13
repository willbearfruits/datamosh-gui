"""Centre panel: inline video preview with play/pause/scrub controls and live re-mosh."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from gui.models.project import Project
from gui.workers.frame_extractor import FrameExtractor
from gui.workers.mosh_worker import MoshWorker


class PreviewWidget(QWidget):
    """Video preview with play/pause/step controls and live mosh pipeline.

    Timeline mode is the default so playback follows sequence cuts/reorders.
    Optional selected-clip mode is available for focused inspection.
    """

    frame_changed = Signal(int)

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._frames: list[QImage] = []
        self._current_frame: int = 0
        self._playing = False
        self._preview_all = True
        self._last_mosh_id: object = None  # tracks what we last moshed
        self._preview_max_frames: Optional[int] = None

        self._play_timer = QTimer(self)
        self._play_timer.setInterval(33)  # ~30fps
        self._play_timer.timeout.connect(self._advance_frame)

        self._mosh_worker: Optional[MoshWorker] = None
        self._extractor: Optional[FrameExtractor] = None
        self._generation = 0          # bumps on every re-mosh; gates stale callbacks
        self._inflight: set = set()   # running QThreads awaiting clean shutdown
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._do_live_mosh)

        self._temp_dir = Path(tempfile.mkdtemp(prefix="datamosh-preview-"))

        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Video display
        self._display = QLabel()
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setMinimumSize(320, 180)
        self._display.setText("Drop or open a video file to begin")
        self._display.setStyleSheet(
            "background-color: #1a1a1a; color: #666; font-size: 14px;"
        )
        layout.addWidget(self._display, 1)

        # Controls bar
        controls = QHBoxLayout()
        controls.setContentsMargins(8, 4, 8, 4)

        self._btn_prev = QPushButton("<<")
        self._btn_prev.setFixedWidth(36)
        self._btn_prev.setToolTip("Previous frame (Left)")
        self._btn_prev.clicked.connect(self._step_back)
        controls.addWidget(self._btn_prev)

        self._btn_play = QToolButton()
        self._btn_play.setAutoRaise(True)
        self._btn_play.setIconSize(QSize(18, 18))
        self._btn_play.setFixedSize(30, 30)
        self._btn_play.setToolTip("Play/Pause (Space)")
        self._btn_play.clicked.connect(self.toggle_play)
        controls.addWidget(self._btn_play)
        self._set_play_icon()

        self._btn_next = QPushButton(">>")
        self._btn_next.setFixedWidth(36)
        self._btn_next.setToolTip("Next frame (Right)")
        self._btn_next.clicked.connect(self._step_forward)
        controls.addWidget(self._btn_next)

        self._scrubber = QSlider(Qt.Orientation.Horizontal)
        self._scrubber.setRange(0, 0)
        self._scrubber.valueChanged.connect(self._on_scrub)
        # Re-apply the range/label once a drag ends (updates are skipped mid-drag).
        self._scrubber.sliderReleased.connect(self._update_scrub_range)
        controls.addWidget(self._scrubber, 1)

        self._frame_label = QLabel("0/0")
        self._frame_label.setFixedWidth(80)
        self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._frame_label.setStyleSheet("color: #8c8c8c; font-size: 11px;")
        controls.addWidget(self._frame_label)

        controls.addSpacing(8)

        self._btn_mode = QToolButton()
        self._btn_mode.setAutoRaise(True)
        self._btn_mode.setIconSize(QSize(18, 18))
        self._btn_mode.setFixedSize(30, 30)
        self._btn_mode.setToolTip("Toggle timeline preview vs selected clip preview")
        self._btn_mode.clicked.connect(self._toggle_mode)
        controls.addWidget(self._btn_mode)
        self._refresh_mode_button()

        layout.addLayout(controls)

    # -- Public API --------------------------------------------------------

    def on_clip_selected(self, _row: int = -1) -> None:
        """Called when user selects a different clip — force preview refresh."""
        self._last_mosh_id = None  # invalidate cache so we re-mosh the new clip
        self.schedule_update()

    def schedule_update(self, _=None) -> None:
        """Called when clips/settings/selection change; debounces the re-mosh."""
        if self._project.has_timeline_items() or self._project.has_clips():
            self._debounce.start()

    def show_frame(self, index: int) -> None:
        if 0 <= index < len(self._frames):
            self._current_frame = index
            self._show_image(self._frames[index])
            self._scrubber.blockSignals(True)
            self._scrubber.setValue(index)
            self._scrubber.blockSignals(False)
            self._frame_label.setText(f"{index + 1}/{len(self._frames)}")
            self.frame_changed.emit(index)

    def toggle_play(self) -> None:
        if self._playing:
            self._stop_playback()
        else:
            self._start_playback()

    # -- Mode toggle -------------------------------------------------------

    def _toggle_mode(self) -> None:
        self._preview_all = not self._preview_all
        self._refresh_mode_button()
        self._last_mosh_id = None  # force refresh
        self.schedule_update()

    # -- Live mosh pipeline ------------------------------------------------

    def _do_live_mosh(self) -> None:
        """Run rewrite_avi to a temp file, then extract frames."""
        if not self._project.has_timeline_items() and not self._project.has_clips():
            return

        if self._preview_all:
            clips = [c for c in self._project.timeline_render_clips() if c.is_ready()]
            if not clips:
                self._display.setText("Timeline clips are not ready yet...")
                return
        else:
            clip = self._project.selected_clip
            if clip and clip.is_ready():
                clips = [clip]
            else:
                self._display.setText("Selected clip is not ready yet...")
                return

        if not clips:
            return

        # Build an identity for this mosh to avoid redundant work
        mosh_id = (
            self._preview_all,
            tuple(
                (
                    str(c.normalized_path),
                    c.keep_first,
                    c.duplicate_count,
                    c.duplicate_gap,
                    c.drop_first_keyframe,
                    c.keep_keys_spec,
                    c.drop_keys_spec,
                    c.trim_start_frame,
                    c.trim_end_frame,
                    c.drop_first_keyframe_override,
                )
                for c in clips
            ),
        )
        if mosh_id == self._last_mosh_id:
            return
        self._last_mosh_id = mosh_id

        # Supersede in-flight work and start a new generation. Each generation
        # writes to its own temp file and its callbacks are gated by the token, so a
        # detached worker can never mix frames into, or clobber, the current preview.
        self._cancel_workers()
        gen = self._generation
        self._purge_preview_files(keep_gen=gen)

        temp_out = self._temp_dir / f"preview_{gen}.avi"
        worker = MoshWorker(clips, temp_out, self)
        worker.finished_ok.connect(lambda path, g=gen: self._on_mosh_done(g, path))
        worker.error.connect(lambda msg, g=gen: self._on_mosh_error(g, msg))
        worker.finished.connect(lambda w=worker: self._retire_worker(w))
        self._mosh_worker = worker
        self._inflight.add(worker)
        self._preview_max_frames = self._estimate_preview_frame_count(clips)
        worker.start()

        name = "timeline" if self._preview_all else clips[0].label()
        self._display.setText(f"Moshing {name}...")

    def _on_mosh_done(self, gen: int, path: str) -> None:
        if gen != self._generation:
            return  # superseded by a newer re-mosh
        self._frames = []
        self._current_frame = 0

        extractor = FrameExtractor(
            Path(path),
            self,
            max_frames=self._preview_max_frames,
            target_width=640,
        )
        extractor.frame_ready.connect(lambda idx, img, g=gen: self._on_frame_decoded(g, idx, img))
        extractor.all_done.connect(lambda total, g=gen: self._on_extraction_done(g, total))
        extractor.error.connect(lambda msg, g=gen: self._on_mosh_error(g, msg))
        extractor.finished.connect(lambda w=extractor: self._retire_worker(w))
        self._extractor = extractor
        self._inflight.add(extractor)
        extractor.start()

    def _on_frame_decoded(self, gen: int, idx: int, img: QImage) -> None:
        if gen != self._generation:
            return
        self._frames.append(img)
        if idx == 0:
            self._show_image(img)
        self._update_scrub_range()

    def _on_extraction_done(self, gen: int, total: int) -> None:
        if gen != self._generation:
            return
        if self._frames:
            self.show_frame(min(self._current_frame, len(self._frames) - 1))
        self._update_scrub_range()

    def _on_mosh_error(self, gen: int, msg: str) -> None:
        if gen != self._generation:
            return
        self._display.setText(f"Preview error: {msg}")
        self._last_mosh_id = None  # allow retry

    def _cancel_workers(self) -> None:
        # Bump the generation so any outstanding worker callbacks become no-ops,
        # then cooperatively abort both the extractor and the mosh worker (both poll
        # an _abort flag and stop quickly). Nothing is terminate()'d here: a detached
        # worker stops at its next checkpoint and self-retires via `finished`.
        self._generation += 1
        if self._extractor is not None:
            self._extractor.abort()
            self._extractor = None
        if self._mosh_worker is not None:
            self._mosh_worker.abort()
            self._mosh_worker = None

    def _retire_worker(self, worker) -> None:
        self._inflight.discard(worker)
        worker.deleteLater()

    def _purge_preview_files(self, keep_gen: Optional[int] = None) -> None:
        keep = f"preview_{keep_gen}.avi" if keep_gen is not None else None
        for f in self._temp_dir.glob("preview_*.avi"):
            if keep is not None and f.name == keep:
                continue
            try:
                f.unlink()
            except OSError:
                pass  # likely still being written by a detached worker; retry later

    def _update_scrub_range(self) -> None:
        if self._scrubber.isSliderDown():
            return  # don't fight an active scrub-drag
        self._scrubber.blockSignals(True)
        self._scrubber.setRange(0, max(0, len(self._frames) - 1))
        self._scrubber.blockSignals(False)
        self._frame_label.setText(f"{self._current_frame + 1}/{len(self._frames)}")

    def reset(self) -> None:
        """Cancel in-flight work and clear the display (project new/load).

        Waits for the aborted workers to actually finish so the caller can safely
        reclaim clip temp dirs (no rmtree-while-reading race).
        """
        self._debounce.stop()
        self._stop_playback()
        self._cancel_workers()
        for worker in list(self._inflight):
            if worker.isRunning():
                worker.wait(2000)
        self._frames = []
        self._current_frame = 0
        self._last_mosh_id = None
        self._scrubber.blockSignals(True)
        self._scrubber.setRange(0, 0)
        self._scrubber.setValue(0)
        self._scrubber.blockSignals(False)
        self._frame_label.setText("0/0")
        self._display.setPixmap(QPixmap())
        self._display.setText("Drop or open a video file to begin")

    def shutdown(self) -> None:
        """Stop preview timers/workers and clean temp files."""
        self._debounce.stop()
        self._stop_playback()
        self._cancel_workers()
        # Wait for aborted workers to finish so no QThread is destroyed while still
        # running. As a last resort at process exit only, terminate a worker that
        # won't stop (e.g. stuck in a large write) — acceptable since we rmtree the
        # temp dir immediately after.
        for worker in list(self._inflight):
            if worker.isRunning() and not worker.wait(3000):
                worker.terminate()
                worker.wait(500)
        self._inflight.clear()
        shutil.rmtree(self._temp_dir, ignore_errors=True)

    # -- Playback controls -------------------------------------------------

    def _start_playback(self) -> None:
        if not self._frames:
            return
        self._playing = True
        self._set_play_icon()
        self._play_timer.start()

    def _stop_playback(self) -> None:
        self._playing = False
        self._set_play_icon()
        self._play_timer.stop()

    def _advance_frame(self) -> None:
        if not self._frames:
            self._stop_playback()
            return
        next_idx = (self._current_frame + 1) % len(self._frames)
        self.show_frame(next_idx)

    def _step_forward(self) -> None:
        self._stop_playback()
        if self._frames:
            self.show_frame(min(self._current_frame + 1, len(self._frames) - 1))

    def _step_back(self) -> None:
        self._stop_playback()
        if self._frames:
            self.show_frame(max(self._current_frame - 1, 0))

    def _on_scrub(self, value: int) -> None:
        self._stop_playback()
        self.show_frame(value)

    # -- Display -----------------------------------------------------------

    def _show_image(self, img: QImage) -> None:
        pix = QPixmap.fromImage(img)
        display_size = self._display.size()
        scaled = pix.scaled(
            display_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self._display.setPixmap(scaled)

    def _set_play_icon(self) -> None:
        sp = (
            QStyle.StandardPixmap.SP_MediaPause
            if self._playing
            else QStyle.StandardPixmap.SP_MediaPlay
        )
        self._btn_play.setIcon(self.style().standardIcon(sp))

    def _refresh_mode_button(self) -> None:
        if self._preview_all:
            icon = self._theme_icon(
                ["view-media-playlist", "view-list-details"],
                QStyle.StandardPixmap.SP_FileDialogDetailedView,
            )
            self._btn_mode.setToolTip("Timeline mode (click for selected clip mode)")
        else:
            icon = self._theme_icon(
                ["video-x-generic", "media-playback-start"],
                QStyle.StandardPixmap.SP_FileIcon,
            )
            self._btn_mode.setToolTip("Selected clip mode (click for timeline mode)")
        self._btn_mode.setIcon(icon)

    def _theme_icon(self, names: list[str], fallback: QStyle.StandardPixmap) -> QIcon:
        for name in names:
            icon = QIcon.fromTheme(name)
            if not icon.isNull():
                return icon
        return self.style().standardIcon(fallback)

    @staticmethod
    def _estimate_preview_frame_count(clips) -> Optional[int]:
        """Estimate frame count for extractor; None means unbounded decode."""
        if not clips:
            return None
        if any(c.total_frames <= 0 for c in clips):
            return None

        total = 0
        for clip in clips:
            start = max(0, clip.trim_start_frame)
            end = clip.trim_end_frame if clip.trim_end_frame > 0 else clip.total_frames
            end = max(start + 1, min(end, clip.total_frames))
            source_frames = max(1, end - start)
            dup_count = max(0, clip.duplicate_count)
            dup_gap = max(1, clip.duplicate_gap)
            # Conservative upper bound so extraction doesn't truncate duplicated output.
            total += source_frames + (source_frames // dup_gap) * dup_count
        return max(1, total)
