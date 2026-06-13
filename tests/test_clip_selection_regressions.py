"""Regression tests for the clip selection / reorder / temp-cleanup bugs.

Covers three data-integrity bugs where editing operations silently bound the
settings panel to the wrong clip or destroyed media still reachable via undo:

* Removing the selected (non-last) clip left the settings panel bound to the
  deleted row (no clip_selected re-emit because the row index was unchanged).
* Clip-bin drag-reorder bypassed Project entirely (no undo, stale selection,
  no clips_changed), so edits landed on the wrong clip and could not be undone.
* Removing a clip eagerly rmtree'd its normalized temp dir, so an undo restored
  a clip reporting is_ready()==True whose media file was already gone.
"""

import pytest
from pathlib import Path

from PySide6.QtCore import QMimeData, QModelIndex, Qt

from gui.models.clip_model import ClipProfile, ClipListModel
from gui.models.project import Project


@pytest.fixture
def project(qtbot):  # qtbot ensures a QApplication exists
    return Project()


def _clips(*names):
    return [ClipProfile(source_path=Path(f"/tmp/{n}.mp4")) for n in names]


# -- Selection rebind on removal ------------------------------------------------

def test_remove_selected_nonlast_clip_rebinds_selection(project):
    a, b, c = _clips("a", "b", "c")
    for clip in (a, b, c):
        project.add_clip(clip, add_to_timeline=False)
    project.select_clip(1)
    assert project.selected_clip is b

    seen: list[int] = []
    project.clip_selected.connect(seen.append)
    project.remove_clip(1)

    assert len(project.clips) == 2
    # Row 1 is now the old clip c; selection must follow it, not the deleted b.
    assert project.selected_clip is c
    assert seen and seen[-1] == 1  # re-emitted despite the row index being unchanged


def test_remove_clip_before_selection_keeps_identity_and_resyncs(project):
    a, b, c = _clips("a", "b", "c")
    for clip in (a, b, c):
        project.add_clip(clip, add_to_timeline=False)
    project.select_clip(2)
    assert project.selected_clip is c

    seen: list[int] = []
    project.clip_selected.connect(seen.append)
    project.remove_clip(0)  # removing an earlier row shifts the selection down

    assert len(project.clips) == 2
    assert project.selected_clip is c        # same object, now at row 1
    assert project.selected_row == 1
    assert seen and seen[-1] == 1            # settings panel rebinds to the new row


def test_remove_midtimeline_clip_follows_selected_segment(project):
    # timeline [a, x, b, c] with the b segment selected; removing the x segment
    # (before it) must follow b to its new index, not leave selection pointing at c.
    a, x, b, c = _clips("a", "x", "b", "c")
    for clip in (a, x, b, c):
        project.add_clip(clip)  # add_to_timeline=True
    project.select_timeline_item(2)
    assert project.timeline_items[2].clip is b

    project.remove_clip(project.row_for_clip(x))

    assert len(project.timeline_items) == 3
    assert project.selected_timeline_index == 1
    assert project.timeline_items[project.selected_timeline_index].clip is b


def test_remove_last_clip_clears_selection(project):
    (a,) = _clips("a")
    project.add_clip(a, add_to_timeline=False)
    project.select_clip(0)
    seen: list[int] = []
    project.clip_selected.connect(seen.append)
    project.remove_clip(0)
    assert project.selected_clip is None
    assert project.selected_row == -1
    assert seen and seen[-1] == -1


# -- Drag-reorder routed through Project ---------------------------------------

def _drop(model: ClipListModel, source_row: int, drop_row: int) -> bool:
    mime = QMimeData()
    mime.setData(model.MIME_TYPE, str(source_row).encode())
    return model.dropMimeData(mime, Qt.DropAction.MoveAction, drop_row, 0, QModelIndex())


def test_drag_reorder_is_undoable_and_follows_selection(project):
    a, b, c = _clips("a", "b", "c")
    for clip in (a, b, c):
        project.add_clip(clip, add_to_timeline=False)
    project.select_clip(1)  # b

    changed: list[int] = []
    project.clips_changed.connect(lambda: changed.append(1))

    assert _drop(project.clip_model, source_row=2, drop_row=0) is True
    # c moved to the front: [c, a, b]
    assert project.clips[0] is c and project.clips[1] is a and project.clips[2] is b
    assert changed                                   # clips_changed fired (preview refresh)
    assert project.selected_clip is b                # selection followed the moved clip
    assert project.selected_row == 2

    assert project.undo() is True                    # reorder is undoable
    assert project.clips[0] is a and project.clips[1] is b and project.clips[2] is c


def test_dropmimedata_rejects_malformed_payloads(project):
    model = project.clip_model
    for clip in _clips("a", "b"):
        project.add_clip(clip, add_to_timeline=False)

    wrong_action = QMimeData()
    wrong_action.setData(model.MIME_TYPE, b"0")
    assert model.dropMimeData(wrong_action, Qt.DropAction.CopyAction, 0, 0, QModelIndex()) is False

    empty = QMimeData()
    empty.setData(model.MIME_TYPE, b"")
    assert model.dropMimeData(empty, Qt.DropAction.MoveAction, 0, 0, QModelIndex()) is False

    garbage = QMimeData()
    garbage.setData(model.MIME_TYPE, b"not-an-int")
    assert model.dropMimeData(garbage, Qt.DropAction.MoveAction, 0, 0, QModelIndex()) is False


# -- Deferred temp-dir cleanup -------------------------------------------------

def _normalized_clip(tmp_path: Path, name: str) -> tuple[ClipProfile, Path]:
    tdir = tmp_path / f"datamosh-norm-{name}"
    tdir.mkdir()
    media = tdir / f"{name}_normalized.avi"
    media.write_bytes(b"FAKE-AVI")
    clip = ClipProfile(source_path=Path(f"/tmp/{name}.mp4"))
    clip.normalized_path = media
    clip.temp_dir = tdir
    return clip, media


def test_remove_then_undo_preserves_normalized_media(project, tmp_path):
    clip, media = _normalized_clip(tmp_path, "x")
    project.add_clip(clip, add_to_timeline=False)
    assert clip.is_ready()

    project.remove_clip(0)
    # The undo snapshot still references the clip, so its media must survive.
    assert media.exists()

    assert project.undo() is True
    assert clip in project.clips
    assert clip.is_ready()
    assert media.exists()  # restored clip's media is intact, not a dangling path


def test_remove_without_undo_reaps_temp_dir(project, tmp_path):
    clip, media = _normalized_clip(tmp_path, "y")
    tdir = clip.temp_dir
    project.add_clip(clip, record_undo=False, add_to_timeline=False)
    assert tdir.exists()

    project.remove_clip(0, record_undo=False)
    # No history references the clip, so its temp dir is reaped immediately.
    assert not tdir.exists()


def test_cleanup_all_removes_every_temp_dir(project, tmp_path):
    clip_a, _ = _normalized_clip(tmp_path, "a")
    clip_b, _ = _normalized_clip(tmp_path, "b")
    project.add_clip(clip_a, record_undo=False, add_to_timeline=False)
    project.add_clip(clip_b, record_undo=False, add_to_timeline=False)
    dirs = [clip_a.temp_dir, clip_b.temp_dir]
    assert all(d.exists() for d in dirs)

    project.cleanup_all()
    assert all(not d.exists() for d in dirs)
