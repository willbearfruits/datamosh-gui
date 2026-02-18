"""Normalization settings dialog."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QComboBox,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

import mosh


class NormalizeDialog(QDialog):
    """Dialog for choosing normalization preset and parameters."""

    def __init__(self, parent=None, *, initial: dict[str, Any] | None = None) -> None:
        super().__init__(parent)
        self._initial = initial or {}
        self.setWindowTitle("Normalization Settings")
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)

        self._info = QLabel(
            "Configure how imported clips are handled before timeline editing."
        )
        self._info.setWordWrap(True)
        layout.addWidget(self._info)

        self._mode_hint = QLabel("")
        self._mode_hint.setWordWrap(True)
        self._mode_hint.setStyleSheet("color: #9bb3d6; font-size: 11px;")
        layout.addWidget(self._mode_hint)

        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Normalize all clips (recommended)", "normalize")
        self.mode_combo.addItem("Use source AVI when possible (advanced)", "prefer_source")
        form.addRow("Import mode:", self.mode_combo)

        info = QLabel("Normalization parameters (used for all clips in this import):")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.preset_combo = QComboBox()
        for name in sorted(mosh.NORMALIZE_PRESETS.keys()):
            cfg = mosh.NORMALIZE_PRESETS[name]
            self.preset_combo.addItem(f"{name.title()} ({cfg['width']}px, q{cfg['qscale']})", name)
        form.addRow("Preset:", self.preset_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 7680)
        self.width_spin.setSpecialValueText("Preset")
        self.width_spin.setSingleStep(2)
        form.addRow("Width:", self.width_spin)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(0, 4320)
        self.height_spin.setSpecialValueText("Auto")
        self.height_spin.setSingleStep(2)
        form.addRow("Height:", self.height_spin)

        self.gop_spin = QSpinBox()
        self.gop_spin.setRange(0, 999)
        self.gop_spin.setSpecialValueText("Preset")
        self.gop_spin.setToolTip("Keyframe interval (GOP). Lower = more keyframes to remove")
        form.addRow("GOP:", self.gop_spin)

        self.qscale_spin = QSpinBox()
        self.qscale_spin.setRange(0, 31)
        self.qscale_spin.setSpecialValueText("Preset")
        self.qscale_spin.setToolTip("Quality (lower = better)")
        form.addRow("Quality:", self.qscale_spin)

        self.keep_audio = QCheckBox("Keep audio")
        self.keep_audio.setChecked(True)
        form.addRow("", self.keep_audio)

        self.remember_defaults = QCheckBox("Remember these settings as default")
        self.remember_defaults.setChecked(True)
        form.addRow("", self.remember_defaults)

        layout.addLayout(form)

        self.mode_combo.currentIndexChanged.connect(self._update_mode_hint)
        self.preset_combo.currentIndexChanged.connect(self._apply_preset)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._apply_initial()

    def _apply_preset(self) -> None:
        name = self.preset_combo.currentData()
        cfg = mosh.NORMALIZE_PRESETS.get(name, {})
        if "width" in cfg:
            self.width_spin.setValue(cfg["width"])
        if "gop" in cfg:
            self.gop_spin.setValue(cfg["gop"])
        if "qscale" in cfg:
            self.qscale_spin.setValue(cfg["qscale"])

    def _apply_initial(self) -> None:
        self._set_combo_by_data(self.mode_combo, self._initial.get("mode", "normalize"))
        self._set_combo_by_data(self.preset_combo, self._initial.get("preset", "balanced"))

        # Start from selected preset defaults, then apply explicit overrides.
        self._apply_preset()

        self.width_spin.setValue(int(self._initial.get("width") or 0))
        self.height_spin.setValue(int(self._initial.get("height") or 0))
        self.gop_spin.setValue(int(self._initial.get("gop") or 0))
        self.qscale_spin.setValue(int(self._initial.get("qscale") or 0))
        self.keep_audio.setChecked(bool(self._initial.get("keep_audio", True)))
        self.remember_defaults.setChecked(bool(self._initial.get("remember_defaults", True)))
        self._update_mode_hint()

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, value: object) -> None:
        idx = combo.findData(value)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _update_mode_hint(self) -> None:
        mode = self.mode_combo.currentData()
        if mode == "prefer_source":
            self._mode_hint.setText(
                "Advanced mode: AVI clips with compatible MPEG-4/Xvid video may skip normalization. "
                "Other clips still normalize automatically."
            )
        else:
            self._mode_hint.setText(
                "Recommended mode: every clip is normalized to a stable Xvid AVI ingest format."
            )

    def get_settings(self) -> dict[str, Any]:
        return {
            "mode": self.mode_combo.currentData(),
            "preset": self.preset_combo.currentData(),
            "width": self.width_spin.value() or None,
            "height": self.height_spin.value() or None,
            "gop": self.gop_spin.value() or None,
            "qscale": self.qscale_spin.value() or None,
            "keep_audio": self.keep_audio.isChecked(),
            "remember_defaults": self.remember_defaults.isChecked(),
        }
