"""Background worker: extract keyframe positions via ffprobe."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QThread, Signal


@dataclass
class FrameInfo:
    """Lightweight frame descriptor for the timeline."""

    index: int
    is_keyframe: bool
    pts_time: float


class KeyframeAnalyzer(QThread):
    """Runs ffprobe to extract frame types for a video file."""

    finished_ok = Signal(list)  # list[FrameInfo]
    error = Signal(str)

    def __init__(self, video_path: Path, parent=None) -> None:
        super().__init__(parent)
        self._path = video_path

    def run(self) -> None:
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-select_streams", "v:0",
                    "-show_entries", "packet=pts_time,flags",
                    "-of", "json",
                    str(self._path),
                ],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                self.error.emit(f"ffprobe exited with code {result.returncode}")
                return

            data = json.loads(result.stdout)
            packets = data.get("packets", [])
            frames: list[FrameInfo] = []
            for i, pkt in enumerate(packets):
                flags = pkt.get("flags", "")
                pts = float(pkt.get("pts_time", 0))
                frames.append(FrameInfo(
                    index=i,
                    is_keyframe="K" in flags,
                    pts_time=pts,
                ))
            self.finished_ok.emit(frames)

        except Exception as exc:
            self.error.emit(str(exc))
