"""Project state container: owns the clip model and coordinates signals."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal

from gui.models.clip_model import ClipListModel, ClipProfile


@dataclass
class TimelineItem:
    """One timeline segment referencing a source clip."""

    clip: ClipProfile
    in_frame: int = 0
    out_frame: int = 0  # exclusive; 0 means "full clip"
    drop_first_keyframe_override: Optional[bool] = None


@dataclass
class ProjectSnapshot:
    """Undo/redo snapshot of editable project state."""

    clips: list[ClipProfile]
    clip_states: list[tuple[int, int, int, bool, str, str]]
    timeline: list[tuple[int, int, int, Optional[bool]]]
    selected_row: int
    selected_timeline_index: int


class Project(QObject):
    """Central state for the current datamosh session."""

    clips_changed = Signal()       # emitted when clips are added/removed/reordered
    clip_selected = Signal(int)    # emitted with the row index of newly selected clip
    clip_updated = Signal(int)     # emitted when a clip's settings change
    timeline_changed = Signal()    # emitted when timeline edits occur
    timeline_item_selected = Signal(int)  # emitted with selected timeline index
    history_changed = Signal(bool, bool)  # can_undo, can_redo
    status_message = Signal(str)   # forwarded to status bar

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.clip_model = ClipListModel(self)
        self._selected_row: int = -1
        self._timeline: list[TimelineItem] = []
        self._selected_timeline_index: int = -1
        self._undo_stack: list[ProjectSnapshot] = []
        self._redo_stack: list[ProjectSnapshot] = []
        self._history_limit = 200
        self._restoring_history = False

    # -- Properties --------------------------------------------------------

    @property
    def clips(self) -> list[ClipProfile]:
        return self.clip_model.clips

    @property
    def selected_row(self) -> int:
        return self._selected_row

    @property
    def selected_clip(self) -> Optional[ClipProfile]:
        return self.clip_model.clip_at(self._selected_row)

    @property
    def timeline_items(self) -> list[TimelineItem]:
        return self._timeline

    @property
    def selected_timeline_index(self) -> int:
        return self._selected_timeline_index

    def has_clips(self) -> bool:
        return self.clip_model.rowCount() > 0

    def has_timeline_items(self) -> bool:
        return bool(self._timeline)

    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def begin_undo_step(self) -> None:
        """Record current state so subsequent edits can be undone."""
        self._record_undo_state()

    def all_ready(self) -> bool:
        return all(c.is_ready() for c in self.clips)

    def timeline_all_ready(self) -> bool:
        return bool(self._timeline) and all(i.clip.is_ready() for i in self._timeline)

    # -- Clip management ---------------------------------------------------

    def add_clip(self, clip: ClipProfile, *, record_undo: bool = True) -> int:
        if record_undo:
            self._record_undo_state()
        row = self.clip_model.add_clip(clip)
        self.clips_changed.emit()
        self.insert_timeline_clip(clip, record_undo=False)
        if self._selected_row < 0:
            self.select_clip(row)
        return row

    def remove_clip(self, row: int, *, record_undo: bool = True) -> None:
        clip = self.clip_model.clip_at(row)
        if clip is None:
            return
        if record_undo:
            self._record_undo_state()
        self.clip_model.remove_clip(row)
        self.clips_changed.emit()

        if clip is not None:
            removed = 0
            kept: list[TimelineItem] = []
            for item in self._timeline:
                if item.clip is clip:
                    removed += 1
                else:
                    kept.append(item)
            if removed:
                old_sel = self._selected_timeline_index
                self._timeline = kept
                if not self._timeline:
                    self._selected_timeline_index = -1
                elif old_sel >= len(self._timeline):
                    self._selected_timeline_index = len(self._timeline) - 1
                self.timeline_changed.emit()
                self.timeline_item_selected.emit(self._selected_timeline_index)

        if row == self._selected_row:
            new = min(row, self.clip_model.rowCount() - 1)
            self.select_clip(new)
        elif row < self._selected_row:
            self._selected_row -= 1

    def select_clip(self, row: int) -> None:
        if row == self._selected_row:
            return
        self._selected_row = row
        self.clip_selected.emit(row)

    def notify_clip_updated(self, row: int, *, record_undo: bool = True) -> None:
        if not (0 <= row < self.clip_model.rowCount()):
            return
        if record_undo:
            self._record_undo_state()
        self.clip_model.update_clip(row)
        self.clip_updated.emit(row)
        self.clips_changed.emit()

    # -- Timeline management ----------------------------------------------

    def row_for_clip(self, clip: ClipProfile) -> int:
        for row, cur in enumerate(self.clips):
            if cur is clip:
                return row
        return -1

    def insert_timeline_from_row(
        self,
        row: int,
        index: Optional[int] = None,
        *,
        record_undo: bool = True,
    ) -> bool:
        clip = self.clip_model.clip_at(row)
        if not clip:
            return False
        self.insert_timeline_clip(clip, index=index, record_undo=record_undo)
        return True

    def insert_timeline_clip(
        self,
        clip: ClipProfile,
        index: Optional[int] = None,
        *,
        record_undo: bool = True,
    ) -> int:
        if record_undo:
            self._record_undo_state()
        item = TimelineItem(clip=clip)
        if index is None:
            index = len(self._timeline)
        index = max(0, min(index, len(self._timeline)))
        self._timeline.insert(index, item)
        self.timeline_changed.emit()
        self.select_timeline_item(index)
        return index

    def remove_timeline_item(self, index: int, *, record_undo: bool = True) -> bool:
        if not (0 <= index < len(self._timeline)):
            return False
        if record_undo:
            self._record_undo_state()
        self._timeline.pop(index)
        if not self._timeline:
            new_idx = -1
        else:
            new_idx = min(index, len(self._timeline) - 1)
        self.timeline_changed.emit()
        self.select_timeline_item(new_idx)
        return True

    def move_timeline_item(self, from_index: int, to_index: int, *, record_undo: bool = True) -> bool:
        n = len(self._timeline)
        if not (0 <= from_index < n):
            return False
        if from_index == to_index or (from_index + 1 == to_index):
            return False
        if record_undo:
            self._record_undo_state()
        to_index = max(0, min(to_index, n))
        item = self._timeline.pop(from_index)
        if to_index > from_index:
            to_index -= 1
        self._timeline.insert(to_index, item)
        self.timeline_changed.emit()
        self.select_timeline_item(to_index)
        return True

    def select_timeline_item(self, index: int) -> None:
        if not self._timeline:
            index = -1
        elif index < 0:
            index = 0
        elif index >= len(self._timeline):
            index = len(self._timeline) - 1

        if index == self._selected_timeline_index:
            return
        self._selected_timeline_index = index
        self.timeline_item_selected.emit(index)

    def split_timeline_item(self, index: int, local_frame: int, *, record_undo: bool = True) -> bool:
        if not (0 <= index < len(self._timeline)):
            return False
        item = self._timeline[index]
        total = item.clip.total_frames
        if total <= 1:
            return False

        start = max(0, item.in_frame)
        end = item.out_frame if item.out_frame > 0 else total
        end = min(end, total)
        length = end - start
        if length <= 1:
            return False
        if record_undo:
            self._record_undo_state()

        cut_local = max(1, min(local_frame, length - 1))
        cut_abs = start + cut_local

        right = TimelineItem(
            clip=item.clip,
            in_frame=cut_abs,
            out_frame=item.out_frame,
            # Default behavior at cuts: drop right-side first I-frame.
            drop_first_keyframe_override=True,
        )
        item.out_frame = cut_abs
        self._timeline.insert(index + 1, right)
        self.timeline_changed.emit()
        self.select_timeline_item(index + 1)
        return True

    def toggle_timeline_item_drop_first(
        self,
        index: int,
        *,
        record_undo: bool = True,
    ) -> Optional[bool]:
        if not (0 <= index < len(self._timeline)):
            return None
        if record_undo:
            self._record_undo_state()
        item = self._timeline[index]
        current = (
            item.drop_first_keyframe_override
            if item.drop_first_keyframe_override is not None
            else item.clip.drop_first_keyframe
        )
        item.drop_first_keyframe_override = not current
        self.timeline_changed.emit()
        return item.drop_first_keyframe_override

    def set_timeline_item_drop_first(
        self,
        index: int,
        enabled: bool,
        *,
        record_undo: bool = True,
    ) -> bool:
        if not (0 <= index < len(self._timeline)):
            return False
        item = self._timeline[index]
        if item.drop_first_keyframe_override == bool(enabled):
            return False
        if record_undo:
            self._record_undo_state()
        item.drop_first_keyframe_override = bool(enabled)
        self.timeline_changed.emit()
        return True

    def timeline_item_effective_drop_first(self, index: int) -> Optional[bool]:
        if not (0 <= index < len(self._timeline)):
            return None
        item = self._timeline[index]
        if item.drop_first_keyframe_override is not None:
            return item.drop_first_keyframe_override
        return item.clip.drop_first_keyframe

    def timeline_render_clips(self) -> list[ClipProfile]:
        """Build a per-segment clip list for mosh workers."""
        out: list[ClipProfile] = []
        for item in self._timeline:
            seg = replace(item.clip)
            seg.trim_start_frame = max(0, item.in_frame)
            seg.trim_end_frame = max(0, item.out_frame)
            seg.drop_first_keyframe_override = item.drop_first_keyframe_override
            out.append(seg)
        return out

    def normalized_paths(self) -> list[Path]:
        """Return normalized paths for all ready clips."""
        return [c.normalized_path for c in self.clips if c.normalized_path]

    # -- Undo/redo --------------------------------------------------------

    def undo(self) -> bool:
        if not self._undo_stack:
            return False
        current = self._capture_snapshot()
        previous = self._undo_stack.pop()
        self._redo_stack.append(current)
        self._restore_snapshot(previous)
        self._emit_history_changed()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        current = self._capture_snapshot()
        nxt = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_snapshot(nxt)
        self._emit_history_changed()
        return True

    def _record_undo_state(self) -> None:
        if self._restoring_history:
            return
        self._undo_stack.append(self._capture_snapshot())
        if len(self._undo_stack) > self._history_limit:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._emit_history_changed()

    def _capture_snapshot(self) -> ProjectSnapshot:
        clips = list(self.clips)
        clip_states = [
            (
                c.keep_first,
                c.duplicate_count,
                c.duplicate_gap,
                c.drop_first_keyframe,
                c.keep_keys_spec,
                c.drop_keys_spec,
            )
            for c in clips
        ]
        idx_map = {id(c): i for i, c in enumerate(clips)}
        timeline: list[tuple[int, int, int, Optional[bool]]] = []
        for item in self._timeline:
            clip_idx = idx_map.get(id(item.clip))
            if clip_idx is None:
                continue
            timeline.append(
                (
                    clip_idx,
                    item.in_frame,
                    item.out_frame,
                    item.drop_first_keyframe_override,
                )
            )

        return ProjectSnapshot(
            clips=clips,
            clip_states=clip_states,
            timeline=timeline,
            selected_row=self._selected_row,
            selected_timeline_index=self._selected_timeline_index,
        )

    def _restore_snapshot(self, snap: ProjectSnapshot) -> None:
        self._restoring_history = True
        try:
            clips = list(snap.clips)
            self.clip_model.replace_clips(clips)
            for clip, state in zip(clips, snap.clip_states):
                (
                    clip.keep_first,
                    clip.duplicate_count,
                    clip.duplicate_gap,
                    clip.drop_first_keyframe,
                    clip.keep_keys_spec,
                    clip.drop_keys_spec,
                ) = state

            timeline: list[TimelineItem] = []
            for clip_idx, in_frame, out_frame, drop_override in snap.timeline:
                if 0 <= clip_idx < len(clips):
                    timeline.append(
                        TimelineItem(
                            clip=clips[clip_idx],
                            in_frame=in_frame,
                            out_frame=out_frame,
                            drop_first_keyframe_override=drop_override,
                        )
                    )
            self._timeline = timeline

            n_clips = len(clips)
            if n_clips == 0:
                self._selected_row = -1
            else:
                self._selected_row = max(0, min(snap.selected_row, n_clips - 1))

            n_items = len(self._timeline)
            if n_items == 0:
                self._selected_timeline_index = -1
            else:
                self._selected_timeline_index = max(
                    0,
                    min(snap.selected_timeline_index, n_items - 1),
                )
        finally:
            self._restoring_history = False

        self.clips_changed.emit()
        self.timeline_changed.emit()
        self.clip_selected.emit(self._selected_row)
        self.timeline_item_selected.emit(self._selected_timeline_index)

    def _emit_history_changed(self) -> None:
        self.history_changed.emit(bool(self._undo_stack), bool(self._redo_stack))
