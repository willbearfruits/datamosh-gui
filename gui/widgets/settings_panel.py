"""Right panel: per-clip settings with sliders and spinboxes."""

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QScrollArea,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
)

from gui.models.project import Project


class _LabeledSlider(QWidget):
    """Horizontal slider with label and spinbox."""

    def __init__(self, label: str, lo: int, hi: int, default: int, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        row = QHBoxLayout()
        self._label = QLabel(label)
        self._label.setWordWrap(True)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        row.addWidget(self._label)
        self.spin = QSpinBox()
        self.spin.setRange(lo, hi)
        self.spin.setValue(default)
        self.spin.setMinimumWidth(64)
        self.spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        row.addWidget(self.spin)
        row.setStretch(0, 1)
        layout.addLayout(row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(lo, hi)
        self.slider.setValue(default)
        self.slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.slider)

        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)

    def value(self) -> int:
        return self.spin.value()

    def set_value(self, v: int) -> None:
        self.spin.setValue(v)


class SettingsPanel(QWidget):
    """Per-clip parameter controls."""

    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project = project
        self._current_row = -1
        self._current_timeline_index = -1
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(300)
        self._debounce.timeout.connect(self._push_settings)
        self._build_ui()
        self._project.timeline_item_selected.connect(self.load_timeline_item)

    def _build_ui(self) -> None:
        self.setMinimumWidth(320)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)

        header = QLabel("Settings")
        header.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        self._form = QVBoxLayout(container)
        self._form.setContentsMargins(4, 4, 4, 4)

        self._clip_label = QLabel("No clip selected")
        self._clip_label.setStyleSheet("color: #8c8c8c;")
        self._clip_label.setWordWrap(True)
        self._clip_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._form.addWidget(self._clip_label)

        # Keyframe group
        key_group = QGroupBox("Keyframes")
        key_layout = QVBoxLayout(key_group)

        self._keep_first = _LabeledSlider("Keep extra keyframes after first", 0, 50, 0)
        key_layout.addWidget(self._keep_first)

        self._drop_first_kf = QCheckBox("Drop first keyframe (selected segment)")
        key_layout.addWidget(self._drop_first_kf)

        self._form.addWidget(key_group)

        # Duplication group
        dup_group = QGroupBox("Duplication")
        dup_layout = QVBoxLayout(dup_group)

        self._dup_count = _LabeledSlider("Duplicate count", 0, 50, 0)
        dup_layout.addWidget(self._dup_count)

        self._dup_gap = _LabeledSlider("Duplicate gap (every Nth)", 1, 100, 1)
        dup_layout.addWidget(self._dup_gap)

        self._form.addWidget(dup_group)

        # Advanced group
        adv_group = QGroupBox("Advanced")
        adv_layout = QVBoxLayout(adv_group)

        adv_layout.addWidget(QLabel("Keep specific keyframes (e.g. 0,5,10-12):"))
        self._keep_keys = QLineEdit()
        self._keep_keys.setPlaceholderText("e.g. 0,5,10-12")
        adv_layout.addWidget(self._keep_keys)

        adv_layout.addWidget(QLabel("Drop specific keyframes:"))
        self._drop_keys = QLineEdit()
        self._drop_keys.setPlaceholderText("e.g. 3,7")
        adv_layout.addWidget(self._drop_keys)

        self._form.addWidget(adv_group)

        self._form.addStretch()

        scroll.setWidget(container)
        outer.addWidget(scroll, 1)

        # Connect change signals to debounced push
        self._keep_first.spin.valueChanged.connect(self._on_changed)
        self._dup_count.spin.valueChanged.connect(self._on_changed)
        self._dup_gap.spin.valueChanged.connect(self._on_changed)
        self._drop_first_kf.stateChanged.connect(self._on_drop_first_changed)
        self._keep_keys.textChanged.connect(self._on_changed)
        self._drop_keys.textChanged.connect(self._on_changed)

    # -- Slots -------------------------------------------------------------

    def load_clip(self, row: int) -> None:
        self._current_row = row
        clip = self._project.clip_model.clip_at(row)
        if not clip:
            self._clip_label.setText("No clip selected")
            return

        # If selected timeline item does not map to this source clip, fall back
        # to source-level behavior for drop-first keyframe.
        if not self._timeline_item_matches_current_clip():
            self._current_timeline_index = -1
        self._refresh_clip_label(clip.label())

        # Block signals while populating
        for w in (self._keep_first.spin, self._dup_count.spin, self._dup_gap.spin,
                  self._drop_first_kf, self._keep_keys, self._drop_keys):
            w.blockSignals(True)

        self._keep_first.set_value(clip.keep_first)
        self._dup_count.set_value(clip.duplicate_count)
        self._dup_gap.set_value(clip.duplicate_gap)
        self._drop_first_kf.setChecked(self._effective_drop_first_for_ui(clip))
        self._keep_keys.setText(clip.keep_keys_spec)
        self._drop_keys.setText(clip.drop_keys_spec)

        for w in (self._keep_first.spin, self._dup_count.spin, self._dup_gap.spin,
                  self._drop_first_kf, self._keep_keys, self._drop_keys):
            w.blockSignals(False)

    def load_timeline_item(self, index: int) -> None:
        self._current_timeline_index = index
        if index < 0 or index >= len(self._project.timeline_items):
            return
        item = self._project.timeline_items[index]
        row = self._project.row_for_clip(item.clip)
        if row < 0:
            return
        self._current_row = row
        self.load_clip(row)

    def _on_changed(self) -> None:
        self._debounce.start()

    def _on_drop_first_changed(self) -> None:
        """Apply drop-first immediately so UI feedback matches toolbar action."""
        self._debounce.stop()
        self._apply_drop_first()

    def _push_settings(self) -> None:
        clip = self._project.clip_model.clip_at(self._current_row)
        if not clip:
            return
        self._project.begin_undo_step()
        clip.keep_first = self._keep_first.value()
        clip.duplicate_count = self._dup_count.value()
        clip.duplicate_gap = self._dup_gap.value()
        self._apply_drop_first(record_undo=False, emit_notify=False)
        clip.keep_keys_spec = self._keep_keys.text().strip()
        clip.drop_keys_spec = self._drop_keys.text().strip()
        self._project.notify_clip_updated(self._current_row, record_undo=False)

    def _apply_drop_first(self, *, record_undo: bool = True, emit_notify: bool = True) -> None:
        clip = self._project.clip_model.clip_at(self._current_row)
        if not clip:
            return
        if record_undo:
            self._project.begin_undo_step()
        drop_first = self._drop_first_kf.isChecked()
        if self._timeline_item_matches_current_clip():
            changed = self._project.set_timeline_item_drop_first(
                self._current_timeline_index,
                drop_first,
                record_undo=False,
            )
            if changed and emit_notify:
                self._project.notify_clip_updated(self._current_row, record_undo=False)
        else:
            if clip.drop_first_keyframe != drop_first:
                clip.drop_first_keyframe = drop_first
                if emit_notify:
                    self._project.notify_clip_updated(self._current_row, record_undo=False)

    def _timeline_item_matches_current_clip(self) -> bool:
        idx = self._current_timeline_index
        if idx < 0 or idx >= len(self._project.timeline_items):
            return False
        item = self._project.timeline_items[idx]
        return self._project.row_for_clip(item.clip) == self._current_row

    def _effective_drop_first_for_ui(self, clip) -> bool:
        if self._timeline_item_matches_current_clip():
            val = self._project.timeline_item_effective_drop_first(self._current_timeline_index)
            if val is not None:
                return val
        return clip.drop_first_keyframe

    def _refresh_clip_label(self, clip_name: str) -> None:
        if self._timeline_item_matches_current_clip():
            text = f"{clip_name}  [segment {self._current_timeline_index + 1}]"
        else:
            text = clip_name
        self._clip_label.setText(text)
        self._clip_label.setToolTip(text)
