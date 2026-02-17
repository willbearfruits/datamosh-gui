"""Background worker for ffmpeg normalization to Xvid AVI."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QThread, Signal

import mosh


class NormalizeWorker(QThread):
    """Normalizes a video file to Xvid AVI in a temp directory."""

    progress = Signal(int, int)       # row, percent (0-100)
    finished_ok = Signal(int, str)    # row, output_path
    error = Signal(int, str)          # row, error_message

    def __init__(
        self,
        source: Path,
        row: int,
        parent=None,
        *,
        preset: str = "balanced",
        width: int | None = None,
        height: int | None = None,
        qscale: int | None = None,
        gop: int | None = None,
        keep_audio: bool = True,
    ) -> None:
        super().__init__(parent)
        self._source = source
        self._row = row
        self._preset = preset
        self._width = width
        self._height = height
        self._qscale = qscale
        self._gop = gop
        self._keep_audio = keep_audio

    def run(self) -> None:
        try:
            self.progress.emit(self._row, 0)

            preset_cfg = mosh.NORMALIZE_PRESETS.get(self._preset, mosh.NORMALIZE_PRESETS["balanced"])
            width = self._width if self._width else preset_cfg["width"]
            height = self._height
            qscale = self._qscale if self._qscale else preset_cfg["qscale"]
            gop = self._gop if self._gop else preset_cfg["gop"]
            keep_audio = self._keep_audio

            tmp_dir = Path(tempfile.mkdtemp(prefix="datamosh-norm-"))
            out_path = tmp_dir / f"{self._source.stem}_normalized.avi"

            self.progress.emit(self._row, 10)

            mosh.normalize_to_xvid(
                self._source,
                out_path,
                width=width,
                height=height,
                qscale=qscale,
                gop=gop,
                keep_audio=keep_audio,
            )

            self.progress.emit(self._row, 100)
            self.finished_ok.emit(self._row, str(out_path))

        except Exception as exc:
            self.error.emit(self._row, str(exc))
