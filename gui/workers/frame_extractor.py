"""Background worker: decode video frames for preview display."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QImage

# Try OpenCV first, fall back to ffmpeg pipe
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    HAS_CV2 = False


class FrameExtractor(QThread):
    """Decode frames from a video file, emitting QImages."""

    frame_ready = Signal(int, QImage)  # frame_index, image
    all_done = Signal(int)             # total frame count
    error = Signal(str)

    def __init__(
        self,
        video_path: Path,
        parent=None,
        *,
        max_frames: Optional[int] = None,
        target_width: int = 640,
    ) -> None:
        super().__init__(parent)
        self._path = video_path
        self._max_frames = None if max_frames is None else max(1, int(max_frames))
        self._target_width = target_width
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        if HAS_CV2:
            self._run_cv2()
        else:
            self._run_ffmpeg()

    def _run_cv2(self) -> None:
        cap = cv2.VideoCapture(str(self._path))
        try:
            if not cap.isOpened():
                self.error.emit("Could not open video with OpenCV")
                return

            idx = 0
            while not self._abort and (self._max_frames is None or idx < self._max_frames):
                ret, frame = cap.read()
                if not ret:
                    break

                h, w = frame.shape[:2]
                if w > self._target_width:
                    scale = self._target_width / w
                    new_w = self._target_width
                    new_h = int(h * scale)
                    frame = cv2.resize(frame, (new_w, new_h))

                h, w = frame.shape[:2]
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                img = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                self.frame_ready.emit(idx, img)
                idx += 1

            self.all_done.emit(idx)

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            cap.release()

    def _run_ffmpeg(self) -> None:
        try:
            # Probe dimensions first
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=width,height",
                    "-of", "csv=p=0",
                    str(self._path),
                ],
                capture_output=True, text=True, timeout=5,
            )
            if probe.returncode != 0:
                self.error.emit("ffprobe failed")
                return

            parts = probe.stdout.strip().split(",")
            orig_w, orig_h = int(parts[0]), int(parts[1])
            if orig_w > self._target_width:
                scale = self._target_width / orig_w
                out_w = self._target_width
                out_h = int(orig_h * scale)
                # Make even
                out_h = out_h + (out_h % 2)
            else:
                out_w, out_h = orig_w, orig_h

            cmd = [
                "ffmpeg", "-i", str(self._path),
                "-vf", f"scale={out_w}:{out_h}",
            ]
            if self._max_frames is not None:
                cmd.extend(["-frames:v", str(self._max_frames)])
            cmd.extend([
                "-f", "rawvideo", "-pix_fmt", "rgb24",
                "-v", "quiet",
                "-",
            ])

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            frame_size = out_w * out_h * 3
            idx = 0

            while not self._abort and (self._max_frames is None or idx < self._max_frames):
                data = proc.stdout.read(frame_size)
                if len(data) < frame_size:
                    break
                img = QImage(data, out_w, out_h, out_w * 3, QImage.Format.Format_RGB888).copy()
                self.frame_ready.emit(idx, img)
                idx += 1

            proc.stdout.close()
            if self._abort:
                proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
            self.all_done.emit(idx)

        except Exception as exc:
            self.error.emit(str(exc))
