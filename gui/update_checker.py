"""GitHub release update lookup."""

from __future__ import annotations

import json
import platform
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional

SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$")


@dataclass(frozen=True)
class ReleaseInfo:
    version: str
    tag: str
    title: str
    html_url: str
    download_url: str
    prerelease: bool


@dataclass(frozen=True)
class UpdateResult:
    current_version: str
    latest: Optional[ReleaseInfo]
    error: Optional[str] = None

    @property
    def has_update(self) -> bool:
        return self.latest is not None and self.error is None


def check_for_update(
    *,
    current_version: str,
    repository: str,
    channel: str = "stable",
    timeout: float = 5.0,
) -> UpdateResult:
    releases, err = _fetch_releases(repository, timeout=timeout)
    if err:
        return UpdateResult(current_version=current_version, latest=None, error=err)

    best: Optional[ReleaseInfo] = None
    for rel in releases:
        info = _release_info(rel, channel=channel)
        if info is None:
            continue
        if _is_newer(info.version, current_version):
            if best is None or _is_newer(info.version, best.version):
                best = info

    return UpdateResult(current_version=current_version, latest=best, error=None)


def _fetch_releases(repository: str, timeout: float) -> tuple[list[dict[str, Any]], Optional[str]]:
    url = f"https://api.github.com/repos/{repository}/releases?per_page=30"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "datamosh-gui-update-checker",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.URLError as exc:
        return [], str(exc)
    except Exception as exc:
        return [], str(exc)

    try:
        payload = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        return [], str(exc)

    if not isinstance(payload, list):
        return [], "Unexpected GitHub API payload"

    out: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict):
            out.append(item)
    return out, None


def _release_info(payload: dict[str, Any], *, channel: str) -> Optional[ReleaseInfo]:
    if payload.get("draft"):
        return None

    prerelease = bool(payload.get("prerelease"))
    if channel == "stable" and prerelease:
        return None

    tag = str(payload.get("tag_name", "")).strip()
    version = _normalize_version(tag)
    if version is None:
        return None

    html_url = str(payload.get("html_url", "")).strip()
    if not html_url:
        return None

    assets = payload.get("assets")
    if not isinstance(assets, list):
        assets = []
    download_url = _select_asset_url(assets) or html_url

    title = str(payload.get("name", "")).strip() or tag

    return ReleaseInfo(
        version=version,
        tag=tag,
        title=title,
        html_url=html_url,
        download_url=download_url,
        prerelease=prerelease,
    )


def _select_asset_url(assets: list[Any]) -> str:
    rows: list[tuple[str, str]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name", "")).strip().lower()
        url = str(asset.get("browser_download_url", "")).strip()
        if name and url:
            rows.append((name, url))

    if not rows:
        return ""

    system = platform.system().lower()
    if "windows" in system:
        prefs = ("windows-installer.exe", "windows-portable.zip")
    elif "darwin" in system or "mac" in system:
        prefs = ("macos-installer.dmg", "macos-portable.zip")
    else:
        prefs = ("linux-installer.deb", "linux-portable.tar.gz")

    for suffix in prefs:
        for name, url in rows:
            if name.endswith(suffix):
                return url

    # Fallback: first asset.
    return rows[0][1]


def _normalize_version(version: str) -> Optional[str]:
    m = SEMVER_RE.match(version.strip())
    if not m:
        return None
    major, minor, patch, pre = m.groups()
    base = f"{int(major)}.{int(minor)}.{int(patch)}"
    return f"{base}-{pre}" if pre else base


def _is_newer(candidate: str, current: str) -> bool:
    a = _version_key(candidate)
    b = _version_key(current)
    if a is None or b is None:
        return False
    return a > b


def _version_key(version: str) -> Optional[tuple[int, int, int, tuple[int, ...], tuple]]:
    m = SEMVER_RE.match(version.strip())
    if not m:
        return None
    major, minor, patch, prerelease = m.groups()
    pre_rank = (1,) if prerelease is None else (0,)
    pre_parts = _prerelease_key(prerelease)
    return (int(major), int(minor), int(patch), pre_rank, pre_parts)


def _prerelease_key(prerelease: Optional[str]) -> tuple:
    if prerelease is None:
        return ()
    parts: list[tuple[int, Any]] = []
    for token in prerelease.split("."):
        if token.isdigit():
            parts.append((0, int(token)))
        else:
            parts.append((1, token.lower()))
    return tuple(parts)
