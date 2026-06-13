"""Tests for ClipPanel ingest-cancellation (stale-callback invalidation)."""

import pytest

from gui.models.project import Project
from gui.widgets.clip_panel import ClipPanel


@pytest.fixture
def panel(qtbot):
    widget = ClipPanel(Project())
    qtbot.addWidget(widget)
    return widget


def test_cancel_ingest_bumps_epoch(panel):
    epoch = panel._ingest_epoch
    panel.cancel_ingest()
    assert panel._ingest_epoch == epoch + 1


def test_discard_orphan_removes_temp_dir(panel, tmp_path):
    d = tmp_path / "datamosh-norm-x"
    d.mkdir()
    media = d / "n.avi"
    media.write_bytes(b"x")
    panel._discard_orphan(str(media))
    assert not d.exists()


def test_discard_orphan_is_safe_on_missing_path(panel, tmp_path):
    panel._discard_orphan(str(tmp_path / "nope" / "n.avi"))  # must not raise
