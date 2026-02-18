"""Background worker that creates a single-frame Xvid AVI for timeline I-frame injection."""

from __future__ import annotations

import tempfile
from pathlib import Path
import subprocess

from PySide6.QtCore import QThread, Signal


class IFrameInjectWorker(QThread):
    """Build a single-frame AVI clip from an image or video source."""

    finished_ok = Signal(str, float)  # output_path, fps
    error = Signal(str)

    def __init__(
        self,
        source: Path,
        *,
        width: int | None,
        height: int | None,
        fps: float,
        qscale: int = 3,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._width = width
        self._height = height
        self._fps = fps if fps > 0 else 30.0
        self._qscale = max(1, int(qscale))

    def run(self) -> None:
        try:
            tmp_dir = Path(tempfile.mkdtemp(prefix="datamosh-inject-"))
            out_path = tmp_dir / f"{self._source.stem}_inject_iframe.avi"

            scale = None
            if self._width and self._height:
                scale = (
                    f"scale={self._width}:{self._height}:flags=lanczos:force_original_aspect_ratio=decrease,"
                    f"pad={self._width}:{self._height}:(ow-iw)/2:(oh-ih)/2"
                )
            elif self._width:
                scale = f"scale={self._width}:-2:flags=lanczos"
            elif self._height:
                scale = f"scale=-2:{self._height}:flags=lanczos"

            # Ensure 4:2:0-safe dimensions for libxvid even when source has odd sizes.
            if scale:
                scale = f"{scale},scale=trunc(iw/2)*2:trunc(ih/2)*2"
            else:
                scale = "scale=trunc(iw/2)*2:trunc(ih/2)*2"

            cmd = [
                "ffmpeg",
                "-y",
                "-i",
                str(self._source),
                "-frames:v",
                "1",
                "-r",
                str(self._fps),
                "-c:v",
                "libxvid",
                "-qscale:v",
                str(self._qscale),
                "-g",
                "1",
                "-bf",
                "0",
                "-pix_fmt",
                "yuv420p",
                "-an",
            ]
            cmd.extend(["-vf", scale])
            cmd.append(str(out_path))

            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                details = (proc.stderr or proc.stdout or "").strip()
                raise RuntimeError(details or "ffmpeg failed to build inject clip")
            self.finished_ok.emit(str(out_path), float(self._fps))
        except Exception as exc:
            self.error.emit(str(exc))
