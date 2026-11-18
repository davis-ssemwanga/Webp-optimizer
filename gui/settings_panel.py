"""Section 2: conversion settings."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFormLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton, QRadioButton,
                               QSlider, QSpinBox, QVBoxLayout, QWidget)

from core.compression import LOSSLESS_NOTE, LOSSY_NOTE, ConflictPolicy, ConversionSettings


class SettingsPanel(QGroupBox):
    changed = Signal()
    recursive_toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__("2. Conversion settings", parent)
        self.output_user_edited = False

        # --- output folder -------------------------------------------------------------
        self.out_edit = QLineEdit()
        self.out_edit.setPlaceholderText("Output folder (created automatically)")
        self.out_edit.setAcceptDrops(False)   # let the window handle dropped files
        self.out_button = QPushButton("Browse…")
        out_row = QHBoxLayout()
        out_row.addWidget(self.out_edit, 1)
        out_row.addWidget(self.out_button)
        self.out_hint = QLabel("Originals are never changed or deleted.")
        self.out_hint.setObjectName("hint")

        # --- mode ---------------------------------------------------------------------
        self.lossy_radio = QRadioButton("Lossy (recommended)")
        self.lossless_radio = QRadioButton("Lossless")
        self.lossy_radio.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.lossy_radio)
        mode_row.addWidget(self.lossless_radio)
        mode_row.addStretch(1)
        self.mode_note = QLabel(LOSSY_NOTE)
        self.mode_note.setObjectName("hint")
        self.mode_note.setWordWrap(True)

        # --- quality / effort ---------------------------------------------------------------
        self.quality_slider = QSlider(Qt.Orientation.Horizontal)
        self.quality_slider.setRange(1, 100)
        self.quality_slider.setValue(85)
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(1, 100)
        self.quality_spin.setValue(85)
        quality_row = QHBoxLayout()
        quality_row.addWidget(self.quality_slider, 1)
        quality_row.addWidget(self.quality_spin)

        self.method_spin = QSpinBox()
        self.method_spin.setRange(0, 6)
        self.method_spin.setValue(4)
        self.method_spin.setToolTip("0 = fastest, 6 = slowest but smallest files")
        self.method_hint = QLabel("0 = fastest, 6 = slowest / smallest")
        self.method_hint.setObjectName("hint")
        method_row = QHBoxLayout()
        method_row.addWidget(self.method_spin)
        method_row.addWidget(self.method_hint, 1)

        # --- resizing ---------------------------------------------------------------------
        self.resize_check = QCheckBox("Resize large images (keeps aspect ratio, never upscales)")
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 16383)
        self.width_spin.setValue(1920)
        self.width_spin.setSuffix(" px")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 16383)
        self.height_spin.setValue(1080)
        self.height_spin.setSuffix(" px")
        size_row = QHBoxLayout()
        size_row.addWidget(QLabel("Max width"))
        size_row.addWidget(self.width_spin)
        size_row.addWidget(QLabel("Max height"))
        size_row.addWidget(self.height_spin)
        self.size_widget = QWidget()
        self.size_widget.setLayout(size_row)
        size_row.setContentsMargins(0, 0, 0, 0)
        self.size_widget.setEnabled(False)

        # --- misc ---------------------------------------------------------------------------
        self.recursive_check = QCheckBox("Include subfolders (keeps the folder structure)")
        self.skip_larger_check = QCheckBox("Don't save a WebP that is larger than the original")
        self.conflict_combo = QComboBox()
        self.conflict_combo.addItem("Rename: photo (1).webp", ConflictPolicy.RENAME)
        self.conflict_combo.addItem("Skip existing files", ConflictPolicy.SKIP)
        self.conflict_combo.addItem("Overwrite existing .webp", ConflictPolicy.OVERWRITE)
        self.workers_spin = QSpinBox()
        self.workers_spin.setRange(0, 16)
        self.workers_spin.setSpecialValueText("Auto")
        self.workers_spin.setToolTip("Images converted in parallel. Auto = up to 4.")

        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        form.addRow("Output folder", out_row)
        form.addRow("", self.out_hint)
        form.addRow("Mode", mode_row)
        form.addRow("", self.mode_note)
        form.addRow("Quality", quality_row)
        form.addRow("Effort (0-6)", method_row)
        form.addRow(self.resize_check)
        form.addRow("", self.size_widget)
        form.addRow(self.recursive_check)
        form.addRow(self.skip_larger_check)
        form.addRow("If a file exists", self.conflict_combo)
        form.addRow("Parallel jobs", self.workers_spin)
        QVBoxLayout(self).addLayout(form)

        # --- wiring -------------------------------------------------------------------------
        self.out_button.clicked.connect(self._browse)
        self.out_edit.textEdited.connect(self._user_edited_output)
        self.quality_slider.valueChanged.connect(self.quality_spin.setValue)
        self.quality_spin.valueChanged.connect(self.quality_slider.setValue)
        self.lossless_radio.toggled.connect(self._mode_changed)
        self.resize_check.toggled.connect(self.size_widget.setEnabled)
        self.recursive_check.toggled.connect(self.recursive_toggled)
        for signal in (self.quality_spin.valueChanged, self.method_spin.valueChanged,
                       self.lossless_radio.toggled, self.resize_check.toggled,
                       self.width_spin.valueChanged, self.height_spin.valueChanged):
            signal.connect(self.changed)

    # -- internals --------------------------------------------------------------------------
    def _mode_changed(self, lossless: bool) -> None:
        self.mode_note.setText(LOSSLESS_NOTE if lossless else LOSSY_NOTE)
        self.quality_slider.setEnabled(not lossless)
        self.quality_spin.setEnabled(not lossless)

    def _browse(self) -> None:
        start = self.out_edit.text().strip() or str(Path.home())
        while start and not Path(start).exists():
            parent = str(Path(start).parent)
            if parent == start:
                break
            start = parent
        name = QFileDialog.getExistingDirectory(self, "Choose the output folder", start)
        if name:
            self.out_edit.setText(name)
            self.output_user_edited = True

    def _user_edited_output(self, _text: str) -> None:
        self.output_user_edited = True

    # -- API --------------------------------------------------------------------------------
    def set_output_dir(self, path: Path | None) -> None:
        """Programmatic update (does not count as a user edit)."""
        self.out_edit.setText(str(path) if path else "")

    def reset_output(self) -> None:
        self.output_user_edited = False
        self.out_edit.clear()

    def output_dir_text(self) -> str:
        return self.out_edit.text().strip()

    def recursive(self) -> bool:
        return self.recursive_check.isChecked()

    def read_settings(self) -> ConversionSettings:
        return ConversionSettings(
            quality=self.quality_spin.value(),
            lossless=self.lossless_radio.isChecked(),
            method=self.method_spin.value(),
            resize_enabled=self.resize_check.isChecked(),
            max_width=self.width_spin.value(),
            max_height=self.height_spin.value(),
            conflict_policy=self.conflict_combo.currentData(),
            recursive=self.recursive_check.isChecked(),
            skip_if_larger=self.skip_larger_check.isChecked(),
            workers=self.workers_spin.value(),
        )

    def set_enabled_for_run(self, enabled: bool) -> None:
        self.setEnabled(enabled)
