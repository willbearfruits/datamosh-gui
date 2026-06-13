"""Locate ffmpeg/ffprobe and keep child processes from flashing console windows.

The engine and workers shell out to ``ffmpeg``/``ffprobe`` by bare name, relying
on PATH. On Windows that means (a) a packaged build must ship the binaries and put
them on PATH, and (b) every child process must be created with ``CREATE_NO_WINDOW``
or it flashes a console window in the ``--windowed`` build. Both concerns live here
so the rest of the code (including the untouched ``mosh.py``) needs no changes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

#: Windows flag that prevents a child process from allocating a console window.
_CREATE_NO_WINDOW = 0x08000000


def _bundled_ffmpeg_dir() -> Optional[Path]:
    """Return the bundled ``ffmpeg`` directory in a frozen build, if present.

    The release build is expected to drop ffmpeg.exe/ffprobe.exe into an
    ``ffmpeg`` subfolder of the PyInstaller bundle (see release.yml --add-binary).
    """
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    candidate = Path(base) / "ffmpeg"
    return candidate if candidate.is_dir() else None


def ensure_ffmpeg_on_path() -> None:
    """Prepend a bundled ffmpeg directory to PATH so bare ``ffmpeg``/``ffprobe``
    calls resolve to the shipped binaries. No-op for source/dev runs."""
    bundled = _bundled_ffmpeg_dir()
    if bundled is not None:
        os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")


def missing_ffmpeg_tools() -> list[str]:
    """Return the subset of ('ffmpeg', 'ffprobe') not resolvable on PATH."""
    return [tool for tool in ("ffmpeg", "ffprobe") if shutil.which(tool) is None]


def suppress_subprocess_console() -> None:
    """On Windows, default every child process to ``CREATE_NO_WINDOW``.

    Installs a ``subprocess.Popen`` subclass (which ``run``/``call``/``check_*``
    all funnel through) that adds the flag unless the caller set ``creationflags``.
    This silences the console-window flash from ffmpeg/ffprobe — including the
    calls inside ``mosh.py`` — without editing any call site. Idempotent.
    """
    if sys.platform != "win32":
        return
    base_popen = subprocess.Popen
    if getattr(base_popen, "_datamosh_no_window", False):
        return

    class _NoWindowPopen(base_popen):  # type: ignore[misc, valid-type]
        _datamosh_no_window = True

        def __init__(self, *args, **kwargs):
            if not kwargs.get("creationflags"):
                kwargs["creationflags"] = _CREATE_NO_WINDOW
            super().__init__(*args, **kwargs)

    subprocess.Popen = _NoWindowPopen  # type: ignore[assignment]
