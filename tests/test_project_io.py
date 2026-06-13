"""Tests for .dmosh project serialization and load/clear of project state."""

import json
import pytest
from pathlib import Path

from gui.models.clip_model import ClipProfile
from gui.models.project import Project
from gui.models import project_io


@pytest.fixture
def project(qtbot):  # qtbot ensures a QApplication exists
    return Project()


def test_serialize_captures_clip_settings_and_timeline(project):
    a = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        keep_first=2, duplicate_count=3, duplicate_gap=4,
        drop_first_keyframe=True, keep_keys_spec="0,5", drop_keys_spec="3",
    )
    b = ClipProfile(source_path=Path("/tmp/b.mp4"))
    project.add_clip(a)  # add_to_timeline=True -> a timeline item per clip
    project.add_clip(b)
    project.select_clip(1)
    project.select_timeline_item(0)

    data = project_io.serialize(project, {"mode": "normalize"}, "1.1.5")

    assert data["format"] == project_io.PROJECT_FORMAT
    assert data["version"] == project_io.PROJECT_VERSION
    assert len(data["clips"]) == 2
    c0 = data["clips"][0]
    assert c0["keep_first"] == 2 and c0["duplicate_count"] == 3 and c0["duplicate_gap"] == 4
    assert c0["drop_first_keyframe"] is True
    assert c0["keep_keys_spec"] == "0,5" and c0["drop_keys_spec"] == "3"
    assert len(data["timeline"]) == 2
    assert data["selected_row"] == 1
    assert data["selected_timeline_index"] == 0
    assert data["import_settings"]["mode"] == "normalize"


def test_install_loaded_state_rebuilds_and_resets_history(project):
    a = ClipProfile(
        source_path=Path("/tmp/a.mp4"),
        keep_first=2, duplicate_count=3, duplicate_gap=4,
        drop_first_keyframe=True, keep_keys_spec="0,5", drop_keys_spec="3",
    )
    project.add_clip(a)
    project.add_clip(ClipProfile(source_path=Path("/tmp/b.mp4")))
    project.select_clip(1)
    data = project_io.serialize(project, {}, "1.1.5")

    p2 = Project()
    clips = p2.install_loaded_state(data)

    assert len(clips) == 2
    assert clips[0].keep_first == 2 and clips[0].duplicate_count == 3 and clips[0].duplicate_gap == 4
    assert clips[0].drop_first_keyframe is True
    assert clips[0].keep_keys_spec == "0,5" and clips[0].drop_keys_spec == "3"
    assert len(p2.timeline_items) == 2
    assert p2.selected_row == 1
    # A fresh load is a clean slate: no undo/redo history.
    assert not p2.can_undo() and not p2.can_redo()


def test_write_then_read_roundtrip(project, tmp_path):
    project.add_clip(ClipProfile(source_path=Path("/tmp/a.mp4"), duplicate_count=5))
    path = tmp_path / "proj.dmosh"
    project_io.write_project(path, project, {"preset": "fast"}, "1.1.5")

    data = project_io.read_project(path)
    assert data["clips"][0]["duplicate_count"] == 5
    assert data["import_settings"]["preset"] == "fast"


def test_iframe_clip_roundtrips(project):
    c = ClipProfile(
        source_path=Path("/tmp/img.png"),
        source_kind="iframe", fps=24.0, frame_width=640, frame_height=480,
    )
    project.add_clip(c)
    data = project_io.serialize(project, {}, "1.1.5")
    assert data["clips"][0]["kind"] == "iframe"
    assert data["clips"][0]["iframe_fps"] == 24.0
    assert data["clips"][0]["iframe_width"] == 640

    p2 = Project()
    clips = p2.install_loaded_state(data)
    assert clips[0].source_kind == "iframe"
    assert clips[0].fps == 24.0
    assert clips[0].frame_width == 640


def test_clear_empties_project(project):
    project.add_clip(ClipProfile(source_path=Path("/tmp/a.mp4")))
    assert project.has_clips()
    project.clear()
    assert not project.has_clips()
    assert not project.has_timeline_items()
    assert project.selected_row == -1
    assert not project.can_undo()


def test_open_over_session_reclaims_old_temp_dirs(project, tmp_path):
    tdir = tmp_path / "datamosh-norm-old"
    tdir.mkdir()
    (tdir / "n.avi").write_bytes(b"x")
    old = ClipProfile(source_path=Path("/tmp/old.mp4"))
    old.normalized_path = tdir / "n.avi"
    old.temp_dir = tdir
    project.add_clip(old, record_undo=False, add_to_timeline=False)
    assert tdir.exists()

    data = {
        "format": project_io.PROJECT_FORMAT, "version": 1,
        "clips": [{"kind": "clip", "source_path": "/tmp/new.mp4"}],
        "timeline": [], "selected_row": -1, "selected_timeline_index": -1,
    }
    project.install_loaded_state(data)

    assert not tdir.exists()  # outgoing session's temp dir reclaimed on load
    assert len(project.clips) == 1
    assert str(project.clips[0].source_path).endswith("new.mp4")


def test_per_segment_override_applies_in_render(project):
    a = ClipProfile(source_path=Path("/tmp/a.mp4"), duplicate_count=0)
    project.add_clip(a)  # add_to_timeline -> one timeline item
    assert len(project.timeline_items) == 1
    assert project.update_timeline_item_settings(
        0, keep_first=2, duplicate_count=5, duplicate_gap=3, keep_keys_spec="", drop_keys_spec=""
    )
    segs = project.timeline_render_clips()
    assert segs[0].duplicate_count == 5 and segs[0].keep_first == 2 and segs[0].duplicate_gap == 3
    assert a.duplicate_count == 0  # the source clip itself is untouched


def test_per_segment_override_undoable(project):
    a = ClipProfile(source_path=Path("/tmp/a.mp4"))
    project.add_clip(a)
    project.update_timeline_item_settings(
        0, keep_first=0, duplicate_count=5, duplicate_gap=1, keep_keys_spec="", drop_keys_spec=""
    )
    assert project.timeline_items[0].duplicate_count_override == 5
    assert project.undo()
    assert project.timeline_items[0].duplicate_count_override is None  # back to inherit


def test_per_segment_overrides_roundtrip(project):
    a = ClipProfile(source_path=Path("/tmp/a.mp4"))
    project.add_clip(a)
    project.update_timeline_item_settings(
        0, keep_first=1, duplicate_count=7, duplicate_gap=2, keep_keys_spec="0,3", drop_keys_spec="5"
    )
    data = project_io.serialize(project, {}, "1.1.5")
    assert data["timeline"][0]["duplicate_count_override"] == 7
    p2 = Project()
    p2.install_loaded_state(data)
    item = p2.timeline_items[0]
    assert item.duplicate_count_override == 7 and item.keep_first_override == 1
    assert item.keep_keys_spec_override == "0,3" and item.drop_keys_spec_override == "5"


def test_read_rejects_non_project(tmp_path):
    p = tmp_path / "x.dmosh"
    p.write_text('{"hello": 1}', encoding="utf-8")
    with pytest.raises(project_io.ProjectLoadError):
        project_io.read_project(p)


def test_read_rejects_bad_json(tmp_path):
    p = tmp_path / "x.dmosh"
    p.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(project_io.ProjectLoadError):
        project_io.read_project(p)


def test_read_rejects_newer_version(tmp_path):
    p = tmp_path / "x.dmosh"
    p.write_text(
        json.dumps({"format": project_io.PROJECT_FORMAT, "version": 999, "clips": [], "timeline": []}),
        encoding="utf-8",
    )
    with pytest.raises(project_io.ProjectLoadError):
        project_io.read_project(p)


def test_install_skips_out_of_range_timeline_index(project):
    # A timeline entry pointing past the clip list must be dropped, not crash.
    data = {
        "format": project_io.PROJECT_FORMAT, "version": 1,
        "clips": [{"kind": "clip", "source_path": "/tmp/a.mp4"}],
        "timeline": [{"clip_index": 0, "in_frame": 0, "out_frame": 0,
                      "drop_first_keyframe_override": None},
                     {"clip_index": 7, "in_frame": 0, "out_frame": 0,
                      "drop_first_keyframe_override": None}],
        "selected_row": 0, "selected_timeline_index": 0,
    }
    clips = project.install_loaded_state(data)
    assert len(clips) == 1
    assert len(project.timeline_items) == 1  # the bogus index-7 entry is dropped
