"""Section 1: choose images or a folder."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

IMAGE_FILTER = "Images (*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG);;All files (*)"


class SourcePanel(QGroupBox):
    selection_changed = Signal(list)   # list[Path]

    def __init__(self, parent=None):
        super().__init__("1. Source", parent)
        self._last_dir = str(Path.home())

        self.files_button = QPushButton("Select Images…")
        self.folder_button = QPushButton("Select Folder…")
        self.path_label = QLabel("No source selected. Choose images or a folder, or drag them here.")
        self.path_label.setWordWrap(True)
        self.count_label = QLabel("")
        self.count_label.setObjectName("hint")
        self.count_label.setWordWrap(True)

        buttons = QHBoxLayout()
        buttons.addWidget(self.files_button)
        buttons.addWidget(self.folder_button)
        layout = QVBoxLayout(self)
        layout.addLayout(buttons)
        layout.addWidget(self.path_label)
        layout.addWidget(self.count_label)

        self.files_button.clicked.connect(self._choose_files)
        self.folder_button.clicked.connect(self._choose_folder)

    # -- user actions --------------------------------------------------------------------
    def _choose_files(self) -> None:
        names, _ = QFileDialog.getOpenFileNames(self, "Select images", self._last_dir, IMAGE_FILTER)
        if names:
            self.set_paths([Path(n) for n in names])

    def _choose_folder(self) -> None:
        name = QFileDialog.getExistingDirectory(self, "Select a folder of images", self._last_dir)
        if name:
            self.set_paths([Path(name)])

    # -- API used by the main window ----------------------------------------------------------
    def set_paths(self, paths: list[Path]) -> None:
        if paths:
            first = paths[0]
            self._last_dir = str(first if first.is_dir() else first.parent)
        self.selection_changed.emit(list(paths))

    def clear(self) -> None:
        self.path_label.setText("No source selected. Choose images or a folder, or drag them here.")
        self.count_label.setText("")

    def show_summary(self, paths: list[Path], count: int, errors: list[str]) -> None:
        if not paths:
            self.clear()
            return
        if len(paths) == 1:
            self.path_label.setText(str(paths[0]))
        else:
            self.path_label.setText(f"{len(paths)} sources selected (first: {paths[0]})")
        text = f"{count} supported image{'s' if count != 1 else ''} detected (JPG, JPEG, PNG)"
        if count == 0:
            text += " — nothing to convert here"
        if errors:
            text += f"\n{len(errors)} problem(s) while scanning, e.g. {errors[0]}"
        self.count_label.setText(text)

    def set_enabled_for_run(self, enabled: bool) -> None:
        self.files_button.setEnabled(enabled)
        self.folder_button.setEnabled(enabled)
