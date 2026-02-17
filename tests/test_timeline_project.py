"""Tests for timeline sequence behavior in Project."""

from pathlib import Path

from gui.models.clip_model import ClipProfile
from gui.models.project import Project


def _clip(path: str, frames: int = 120) -> ClipProfile:
    return ClipProfile(source_path=Path(path), total_frames=frames, fps=30.0)


def test_add_clip_populates_timeline(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4")

    project.add_clip(clip)

    assert len(project.timeline_items) == 1
    assert project.timeline_items[0].clip is clip


def test_insert_timeline_from_row_creates_duplicate_segment(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4")
    project.add_clip(clip)

    ok = project.insert_timeline_from_row(0, 1)

    assert ok is True
    assert len(project.timeline_items) == 2
    assert project.timeline_items[0].clip is clip
    assert project.timeline_items[1].clip is clip


def test_move_timeline_item_reorders_segments(qtbot):
    project = Project()
    clip_a = _clip("/tmp/a.mp4")
    clip_b = _clip("/tmp/b.mp4")
    clip_c = _clip("/tmp/c.mp4")
    project.add_clip(clip_a)
    project.add_clip(clip_b)
    project.add_clip(clip_c)

    moved = project.move_timeline_item(0, 3)

    assert moved is True
    assert [i.clip for i in project.timeline_items] == [clip_b, clip_c, clip_a]


def test_split_timeline_item_creates_cut_segments(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4", frames=100)
    project.add_clip(clip)

    split = project.split_timeline_item(0, 30)

    assert split is True
    assert len(project.timeline_items) == 2
    left, right = project.timeline_items
    assert left.in_frame == 0
    assert left.out_frame == 30
    assert right.in_frame == 30
    assert right.out_frame == 0
    assert right.drop_first_keyframe_override is True


def test_toggle_timeline_drop_first_override(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4")
    project.add_clip(clip)

    val1 = project.toggle_timeline_item_drop_first(0)
    val2 = project.toggle_timeline_item_drop_first(0)

    assert val1 is True
    assert val2 is False


def test_set_timeline_drop_first_override(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4")
    project.add_clip(clip)

    ok = project.set_timeline_item_drop_first(0, True)
    effective = project.timeline_item_effective_drop_first(0)

    assert ok is True
    assert effective is True


def test_timeline_render_clips_apply_segment_bounds(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4", frames=90)
    project.add_clip(clip)
    project.split_timeline_item(0, 25)

    segs = project.timeline_render_clips()

    assert len(segs) == 2
    assert segs[0].trim_start_frame == 0
    assert segs[0].trim_end_frame == 25
    assert segs[1].trim_start_frame == 25
    assert segs[1].trim_end_frame == 0
    assert segs[1].drop_first_keyframe_override is True


def test_undo_redo_timeline_split(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4", frames=80)
    project.add_clip(clip)

    assert project.split_timeline_item(0, 20) is True
    assert len(project.timeline_items) == 2

    assert project.undo() is True
    assert len(project.timeline_items) == 1

    assert project.redo() is True
    assert len(project.timeline_items) == 2


def test_undo_clip_setting_change(qtbot):
    project = Project()
    clip = _clip("/tmp/a.mp4")
    row = project.add_clip(clip)

    project.begin_undo_step()
    clip.duplicate_count = 4
    project.notify_clip_updated(row, record_undo=False)
    assert clip.duplicate_count == 4

    assert project.undo() is True
    assert clip.duplicate_count == 0
