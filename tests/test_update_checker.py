"""Tests for release update lookup and version ordering."""

from __future__ import annotations

import gui.update_checker as uc


def _release(tag: str, *, prerelease: bool, assets: list[dict] | None = None) -> dict:
    return {
        "tag_name": tag,
        "name": tag,
        "draft": False,
        "prerelease": prerelease,
        "html_url": f"https://example.com/{tag}",
        "assets": assets or [],
    }


def test_version_normalization() -> None:
    assert uc._normalize_version("v1.2.3") == "1.2.3"
    assert uc._normalize_version("1.2.3-beta.1") == "1.2.3-beta.1"
    assert uc._normalize_version("bad") is None


def test_version_ordering() -> None:
    assert uc._is_newer("1.2.4", "1.2.3")
    assert uc._is_newer("1.3.0", "1.2.9")
    assert uc._is_newer("1.2.3", "1.2.3-beta.1")
    assert uc._is_newer("1.2.3-beta.2", "1.2.3-beta.1")
    assert not uc._is_newer("1.2.3-beta.1", "1.2.3")


def test_check_for_update_stable_channel(monkeypatch) -> None:
    releases = [
        _release("v1.2.1-beta.1", prerelease=True),
        _release("v1.2.0", prerelease=False),
    ]

    monkeypatch.setattr(uc, "_fetch_releases", lambda *_args, **_kwargs: (releases, None))

    out = uc.check_for_update(
        current_version="1.1.0",
        repository="owner/repo",
        channel="stable",
    )

    assert out.error is None
    assert out.latest is not None
    assert out.latest.version == "1.2.0"


def test_check_for_update_prerelease_channel(monkeypatch) -> None:
    releases = [
        _release("v1.2.0", prerelease=False),
        _release("v1.2.1-beta.2", prerelease=True),
    ]

    monkeypatch.setattr(uc, "_fetch_releases", lambda *_args, **_kwargs: (releases, None))

    out = uc.check_for_update(
        current_version="1.2.1-beta.1",
        repository="owner/repo",
        channel="prerelease",
    )

    assert out.error is None
    assert out.latest is not None
    assert out.latest.version == "1.2.1-beta.2"


def test_platform_asset_selection(monkeypatch) -> None:
    assets = [
        {"name": "Datamosh-1.2.0-linux-portable.tar.gz", "browser_download_url": "linux-portable"},
        {"name": "Datamosh-1.2.0-linux-installer.deb", "browser_download_url": "linux-installer"},
    ]
    monkeypatch.setattr(uc.platform, "system", lambda: "Linux")
    assert uc._select_asset_url(assets) == "linux-installer"
