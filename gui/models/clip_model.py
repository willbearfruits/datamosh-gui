"""Clip data model: ClipProfile dataclass and QAbstractListModel."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QAbstractListModel, QMimeData, QModelIndex, Qt
from PySide6.QtGui import QPixmap


@dataclass
class ClipProfile:
    """Per-clip settings and state."""

    source_path: Path
    normalized_path: Optional[Path] = None
    thumbnail: Optional[QPixmap] = None
    keep_first: int = 0
    duplicate_count: int = 0
    duplicate_gap: int = 1
    drop_first_keyframe: bool = False
    keep_keys_spec: str = ""
    drop_keys_spec: str = ""
    normalizing: bool = False
    total_frames: int = 0
    fps: float = 30.0
    frame_width: int = 0
    frame_height: int = 0
    # Timeline segment metadata (used for render/preview clones).
    trim_start_frame: int = 0
    trim_end_frame: int = 0  # exclusive; 0 means "use full clip"
    drop_first_keyframe_override: Optional[bool] = None
    # Temp directory created during normalization or I-frame injection.
    temp_dir: Optional[Path] = field(default=None, repr=False, compare=False)

    def label(self) -> str:
        return self.source_path.stem

    def is_ready(self) -> bool:
        return self.normalized_path is not None and not self.normalizing

    def effective_drop_first_keyframe(self) -> bool:
        if self.drop_first_keyframe_override is not None:
            return self.drop_first_keyframe_override
        return self.drop_first_keyframe

    def cleanup(self) -> None:
        """Delete the temp directory created during normalization or injection."""
        if self.temp_dir and self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)
            self.temp_dir = None


class ClipListModel(QAbstractListModel):
    """List model for ClipProfile objects with drag-reorder support."""

    MIME_TYPE = "application/x-datamosh-clip-index"

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._clips: list[ClipProfile] = []

    # -- Public API --------------------------------------------------------

    @property
    def clips(self) -> list[ClipProfile]:
        return self._clips

    def add_clip(self, clip: ClipProfile) -> int:
        row = len(self._clips)
        self.beginInsertRows(QModelIndex(), row, row)
        self._clips.append(clip)
        self.endInsertRows()
        return row

    def replace_clips(self, clips: list[ClipProfile]) -> None:
        """Replace entire clip order/content and reset model view state."""
        self.beginResetModel()
        self._clips = list(clips)
        self.endResetModel()

    def remove_clip(self, row: int) -> None:
        if 0 <= row < len(self._clips):
            self.beginRemoveRows(QModelIndex(), row, row)
            self._clips.pop(row)
            self.endRemoveRows()

    def move_clip(self, from_row: int, to_row: int) -> None:
        if from_row == to_row:
            return
        n = len(self._clips)
        if not (0 <= from_row < n and 0 <= to_row < n):
            return
        # Qt requires destination row offset for moveRows
        dest = to_row + 1 if to_row > from_row else to_row
        self.beginMoveRows(QModelIndex(), from_row, from_row, QModelIndex(), dest)
        clip = self._clips.pop(from_row)
        self._clips.insert(to_row, clip)
        self.endMoveRows()

    def clip_at(self, row: int) -> Optional[ClipProfile]:
        if 0 <= row < len(self._clips):
            return self._clips[row]
        return None

    def update_clip(self, row: int) -> None:
        if 0 <= row < len(self._clips):
            idx = self.index(row, 0)
            self.dataChanged.emit(idx, idx)

    # -- QAbstractListModel overrides --------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._clips)

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        clip = self._clips[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            suffix = " (normalizing...)" if clip.normalizing else ""
            return f"{clip.label()}{suffix}"
        if role == Qt.ItemDataRole.ToolTipRole:
            return str(clip.source_path)
        if role == Qt.ItemDataRole.DecorationRole:
            return clip.thumbnail
        if role == Qt.ItemDataRole.UserRole:
            return clip
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        default = super().flags(index)
        if index.isValid():
            return default | Qt.ItemFlag.ItemIsDragEnabled
        return default | Qt.ItemFlag.ItemIsDropEnabled

    def supportedDropActions(self) -> Qt.DropAction:
        return Qt.DropAction.MoveAction

    def mimeTypes(self) -> list[str]:
        return [self.MIME_TYPE]

    def mimeData(self, indexes: list[QModelIndex]) -> QMimeData:
        mime = QMimeData()
        rows = ",".join(str(i.row()) for i in indexes if i.isValid())
        mime.setData(self.MIME_TYPE, rows.encode())
        return mime

    def dropMimeData(self, data: QMimeData, action, row, column, parent) -> bool:
        if action != Qt.DropAction.MoveAction:
            return False
        raw = data.data(self.MIME_TYPE)
        if raw.isEmpty():
            return False
        try:
            source_row = int(bytes(raw).decode().split(",")[0])
        except (UnicodeDecodeError, ValueError, IndexError):
            return False
        target = row if row >= 0 else self.rowCount()
        if source_row < target:
            target -= 1
        self.move_clip(source_row, target)
        return True
