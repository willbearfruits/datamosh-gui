"""Normalization settings dialog."""

from PySide6.QtCore import Qt
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

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Normalization Settings")
        self.setMinimumWidth(320)

        layout = QVBoxLayout(self)

        info = QLabel("Configure how video files are converted to Xvid AVI for datamoshing.")
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.preset_combo = QComboBox()
        for name in sorted(mosh.NORMALIZE_PRESETS.keys()):
            cfg = mosh.NORMALIZE_PRESETS[name]
            self.preset_combo.addItem(f"{name.title()} ({cfg['width']}px, q{cfg['qscale']})", name)
        self.preset_combo.setCurrentIndex(1)  # balanced
        form.addRow("Preset:", self.preset_combo)

        self.width_spin = QSpinBox()
        self.width_spin.setRange(0, 7680)
        self.width_spin.setSpecialValueText("Auto")
        self.width_spin.setSingleStep(2)
        form.addRow("Width:", self.width_spin)

        self.gop_spin = QSpinBox()
        self.gop_spin.setRange(1, 999)
        self.gop_spin.setValue(48)
        self.gop_spin.setToolTip("Keyframe interval (GOP). Lower = more keyframes to remove")
        form.addRow("GOP:", self.gop_spin)

        self.qscale_spin = QSpinBox()
        self.qscale_spin.setRange(1, 31)
        self.qscale_spin.setValue(3)
        self.qscale_spin.setToolTip("Quality (lower = better)")
        form.addRow("Quality:", self.qscale_spin)

        self.keep_audio = QCheckBox("Keep audio")
        self.keep_audio.setChecked(True)
        form.addRow("", self.keep_audio)

        layout.addLayout(form)

        self.preset_combo.currentIndexChanged.connect(self._apply_preset)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_preset(self) -> None:
        name = self.preset_combo.currentData()
        cfg = mosh.NORMALIZE_PRESETS.get(name, {})
        if "width" in cfg:
            self.width_spin.setValue(cfg["width"])
        if "gop" in cfg:
            self.gop_spin.setValue(cfg["gop"])
        if "qscale" in cfg:
            self.qscale_spin.setValue(cfg["qscale"])

    def get_settings(self) -> dict:
        return {
            "preset": self.preset_combo.currentData(),
            "width": self.width_spin.value() or None,
            "gop": self.gop_spin.value(),
            "qscale": self.qscale_spin.value(),
            "keep_audio": self.keep_audio.isChecked(),
        }
