"""Application version helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

DEFAULT_VERSION = "0.0.0-dev"
REPOSITORY = "willbearfruits/datamosh-gui"


def _candidate_version_paths() -> list[Path]:
    paths: list[Path] = []

    # Source-tree run.
    root = Path(__file__).resolve().parents[1]
    paths.append(root / "VERSION")

    # PyInstaller one-folder run.
    exe_dir = Path(sys.executable).resolve().parent
    paths.append(exe_dir / "VERSION")

    # PyInstaller temp extraction path for one-file mode.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        paths.append(Path(meipass) / "VERSION")

    return paths


def get_version() -> str:
    env_version = os.getenv("DATAMOSH_VERSION", "").strip()
    if env_version:
        return env_version

    for path in _candidate_version_paths():
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text

    return DEFAULT_VERSION


def release_channel(version: str | None = None) -> str:
    cur = version or get_version()
    return "prerelease" if "-" in cur else "stable"
