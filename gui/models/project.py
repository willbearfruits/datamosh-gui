"""Project state container: owns the clip model and coordinates signals."""

from __future__ import annotations

from collections import deque
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
        self._history_limit = 200
        self._undo_stack: deque[ProjectSnapshot] = deque(maxlen=self._history_limit)
        self._redo_stack: deque[ProjectSnapshot] = deque(maxlen=self._history_limit)
        self._restoring_history = False
        # Clips removed from the model but possibly still referenced by undo/redo
        # history. Their temp dirs are reaped only once truly unreachable, so an
        # undo can never restore a clip whose normalized media file was deleted.
        self._pending_temp_cleanup: list[ClipProfile] = []
        self.clip_model.reorder_requested.connect(self._on_clips_reordered)

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

    def add_clip(
        self,
        clip: ClipProfile,
        *,
        record_undo: bool = True,
        add_to_timeline: bool = True,
    ) -> int:
        if record_undo:
            self._record_undo_state()
        row = self.clip_model.add_clip(clip)
        self.clips_changed.emit()
        if add_to_timeline:
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
        # Defer temp-dir cleanup: the just-recorded undo snapshot still holds this
        # clip (with its normalized_path), so deleting its temp dir now would make a
        # later undo restore a clip whose media file is gone. Reap once unreachable.
        if clip.temp_dir is not None and not any(c is clip for c in self._pending_temp_cleanup):
            self._pending_temp_cleanup.append(clip)
        self.clip_model.remove_clip(row)
        self.clips_changed.emit()

        removed = 0
        kept: list[TimelineItem] = []
        for item in self._timeline:
            if item.clip is clip:
                removed += 1
            else:
                kept.append(item)
        if removed:
            old_sel = self._selected_timeline_index
            selected_item = (
                self._timeline[old_sel] if 0 <= old_sel < len(self._timeline) else None
            )
            self._timeline = kept
            if not self._timeline:
                self._selected_timeline_index = -1
            else:
                # Follow the still-present selected segment to its new index (it may
                # have shifted down if an earlier segment was removed); otherwise the
                # selected segment was one of the removed ones, so clamp into range.
                new_idx = next(
                    (i for i, it in enumerate(self._timeline) if it is selected_item),
                    -1,
                )
                if new_idx >= 0:
                    self._selected_timeline_index = new_idx
                elif old_sel >= len(self._timeline):
                    self._selected_timeline_index = len(self._timeline) - 1
            self.timeline_changed.emit()
            self.timeline_item_selected.emit(self._selected_timeline_index)

        # Keep selection bound to the correct clip. When the removed row is at or
        # before the selection, the clip now occupying that slot (or the shifted
        # selected clip) differs from what the settings panel is bound to, so force
        # a re-emit even when the row index is numerically unchanged.
        old = self._selected_row
        if old >= 0 and row <= old:
            count = self.clip_model.rowCount()
            if count == 0:
                new = -1
            elif row < old:
                new = old - 1
            else:  # row == old
                new = min(row, count - 1)
            self.select_clip(new, force=True)

        self._reap_temp_dirs()

    def select_clip(self, row: int, *, force: bool = False) -> None:
        if row == self._selected_row and not force:
            return
        self._selected_row = row
        self.clip_selected.emit(row)

    def _on_clips_reordered(self, source_row: int, target_row: int) -> None:
        """Perform a drag-drop reorder requested by the clip model: record undo,
        move the clip, and rebind the selection to its new row. The model itself
        only emits the request so the reorder stays undoable and in sync."""
        n = self.clip_model.rowCount()
        if source_row == target_row or not (0 <= source_row < n and 0 <= target_row < n):
            return
        self._record_undo_state()
        selected_clip = self.clip_model.clip_at(self._selected_row)
        self.clip_model.move_clip(source_row, target_row)
        new_row = self.row_for_clip(selected_clip) if selected_clip is not None else -1
        # Force a re-emit so the settings panel rebinds to the moved clip's new row.
        self.select_clip(new_row, force=True)
        self.clips_changed.emit()

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
        self._reap_temp_dirs()
        return True

    def redo(self) -> bool:
        if not self._redo_stack:
            return False
        current = self._capture_snapshot()
        nxt = self._redo_stack.pop()
        self._undo_stack.append(current)
        self._restore_snapshot(nxt)
        self._emit_history_changed()
        self._reap_temp_dirs()
        return True

    def _record_undo_state(self) -> None:
        if self._restoring_history:
            return
        self._undo_stack.append(self._capture_snapshot())
        self._redo_stack.clear()
        self._emit_history_changed()
        self._reap_temp_dirs()

    def _referenced_clip_ids(self) -> set[int]:
        """ids of clips reachable from the live list or undo/redo history."""
        ids = {id(c) for c in self.clips}
        for snap in self._undo_stack:
            ids.update(id(c) for c in snap.clips)
        for snap in self._redo_stack:
            ids.update(id(c) for c in snap.clips)
        return ids

    def _reap_temp_dirs(self) -> None:
        """Delete temp dirs of removed clips no longer reachable from the live list
        or undo/redo history, so an undo can never resurrect deleted media."""
        if not self._pending_temp_cleanup:
            return
        referenced = self._referenced_clip_ids()
        still_pending: list[ClipProfile] = []
        for clip in self._pending_temp_cleanup:
            if id(clip) in referenced:
                still_pending.append(clip)
            else:
                clip.cleanup()
        self._pending_temp_cleanup = still_pending

    def cleanup_all(self) -> None:
        """Delete every temp dir owned by this session. Call on app shutdown."""
        seen: set[int] = set()
        groups: list[list[ClipProfile]] = [list(self.clips), self._pending_temp_cleanup]
        groups += [snap.clips for snap in self._undo_stack]
        groups += [snap.clips for snap in self._redo_stack]
        for group in groups:
            for clip in group:
                if id(clip) in seen:
                    continue
                seen.add(id(clip))
                clip.cleanup()
        self._pending_temp_cleanup = []

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

    # -- Project load/clear -----------------------------------------------

    def clear(self) -> None:
        """Reset to an empty project, reclaiming all temp dirs and history."""
        self.cleanup_all()
        self._restoring_history = True
        try:
            self.clip_model.replace_clips([])
            self._timeline = []
            self._selected_row = -1
            self._selected_timeline_index = -1
        finally:
            self._restoring_history = False
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._pending_temp_cleanup = []
        self.clips_changed.emit()
        self.timeline_changed.emit()
        self.clip_selected.emit(-1)
        self.timeline_item_selected.emit(-1)
        self._emit_history_changed()

    def install_loaded_state(self, data: dict) -> list[ClipProfile]:
        """Rebuild clips + timeline + selection from parsed .dmosh data.

        Returns the freshly-created ClipProfile objects (not yet normalized) so the
        caller can re-ingest each one. History is reset — a load is a clean slate.
        """
        clips: list[ClipProfile] = []
        for spec in data.get("clips", []):
            if not isinstance(spec, dict) or "source_path" not in spec:
                continue
            clip = ClipProfile(
                source_path=Path(spec["source_path"]),
                keep_first=int(spec.get("keep_first", 0) or 0),
                duplicate_count=int(spec.get("duplicate_count", 0) or 0),
                duplicate_gap=max(1, int(spec.get("duplicate_gap", 1) or 1)),
                drop_first_keyframe=bool(spec.get("drop_first_keyframe", False)),
                keep_keys_spec=str(spec.get("keep_keys_spec", "") or ""),
                drop_keys_spec=str(spec.get("drop_keys_spec", "") or ""),
                source_kind=str(spec.get("kind", "clip") or "clip"),
            )
            if clip.source_kind == "iframe":
                clip.fps = float(spec.get("iframe_fps", 30.0) or 30.0)
                clip.frame_width = int(spec.get("iframe_width") or 0)
                clip.frame_height = int(spec.get("iframe_height") or 0)
            clips.append(clip)

        self._restoring_history = True
        try:
            self.clip_model.replace_clips(clips)
            timeline: list[TimelineItem] = []
            for spec in data.get("timeline", []):
                if not isinstance(spec, dict):
                    continue
                ci = spec.get("clip_index", -1)
                if isinstance(ci, int) and 0 <= ci < len(clips):
                    timeline.append(TimelineItem(
                        clip=clips[ci],
                        in_frame=int(spec.get("in_frame", 0) or 0),
                        out_frame=int(spec.get("out_frame", 0) or 0),
                        drop_first_keyframe_override=spec.get("drop_first_keyframe_override"),
                    ))
            self._timeline = timeline
            sr = data.get("selected_row", -1)
            self._selected_row = sr if isinstance(sr, int) and 0 <= sr < len(clips) else -1
            st = data.get("selected_timeline_index", -1)
            self._selected_timeline_index = (
                st if isinstance(st, int) and 0 <= st < len(timeline) else -1
            )
        finally:
            self._restoring_history = False

        self._undo_stack.clear()
        self._redo_stack.clear()
        self._pending_temp_cleanup = []
        self.clips_changed.emit()
        self.timeline_changed.emit()
        self.clip_selected.emit(self._selected_row)
        self.timeline_item_selected.emit(self._selected_timeline_index)
        self._emit_history_changed()
        return clips
