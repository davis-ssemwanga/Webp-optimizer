"""Original-vs-WebP preview using the current settings (nothing is written to disk)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps
from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, Signal
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (QFileDialog, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout, QWidget)

from core.compression import ConversionSettings
from core.converter import encode_webp
from utils.size_formatter import format_percent, format_size, percent_reduction

THUMB = (240, 180)


@dataclass
class _Thumb:
    data: bytes
    width: int
    height: int


@dataclass
class _PreviewData:
    original: _Thumb
    webp: _Thumb
    original_dims: tuple[int, int]
    webp_dims: tuple[int, int]
    original_bytes: int
    webp_bytes: int


def _thumb(img: Image.Image) -> _Thumb:
    img = img.copy()
    img.thumbnail(THUMB, Image.Resampling.LANCZOS)
    rgba = img.convert("RGBA")
    return _Thumb(rgba.tobytes(), rgba.width, rgba.height)


class _Signals(QObject):
    done = Signal(int, object)
    failed = Signal(int, str)


class _PreviewTask(QRunnable):
    def __init__(self, token: int, path: Path, settings: ConversionSettings, signals: _Signals):
        super().__init__()
        self.token, self.path, self.settings, self.signals = token, path, settings, signals

    def run(self) -> None:
        try:
            import io
            encoded = encode_webp(self.path, self.settings)
            with Image.open(self.path) as original:
                original.load()
                oriented = ImageOps.exif_transpose(original)
                original_thumb = _thumb(oriented)
            with Image.open(io.BytesIO(encoded.data)) as webp:
                webp.load()
                webp_thumb = _thumb(webp)
            data = _PreviewData(original_thumb, webp_thumb, encoded.source_size, encoded.output_size,
                                self.path.stat().st_size, len(encoded.data))
            self.signals.done.emit(self.token, data)
        except Exception as exc:  # noqa: BLE001
            self.signals.failed.emit(self.token, str(exc) or type(exc).__name__)


class PreviewPanel(QGroupBox):
    def __init__(self, settings_provider: Callable[[], ConversionSettings], parent=None):
        super().__init__("Preview: compare before converting", parent)
        self._settings_provider = settings_provider
        self._default: Path | None = None
        self._chosen: Path | None = None
        self._token = 0
        self._signals = _Signals()
        self._signals.done.connect(self._on_done)
        self._signals.failed.connect(self._on_failed)

        self.original_image = self._make_image_label()
        self.webp_image = self._make_image_label()
        self.original_info = QLabel("")
        self.webp_info = QLabel("")
        for label in (self.original_info, self.webp_info):
            label.setObjectName("hint")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setWordWrap(True)

        columns = QHBoxLayout()
        columns.addWidget(self._column("Original", self.original_image, self.original_info))
        columns.addWidget(self._column("WebP (current settings)", self.webp_image, self.webp_info))

        self.file_label = QLabel("No image to preview yet.")
        self.file_label.setObjectName("hint")
        self.preview_button = QPushButton("Preview")
        self.choose_button = QPushButton("Choose Image…")
        self.preview_button.clicked.connect(self.refresh)
        self.choose_button.clicked.connect(self._choose)
        controls = QHBoxLayout()
        controls.addWidget(self.file_label, 1)
        controls.addWidget(self.choose_button)
        controls.addWidget(self.preview_button)

        layout = QVBoxLayout(self)
        layout.addLayout(columns)
        layout.addLayout(controls)

    # -- layout helpers ---------------------------------------------------------------------
    def _make_image_label(self) -> QLabel:
        label = QLabel("—")
        label.setObjectName("previewImage")
        label.setFixedSize(*THUMB)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _column(self, title: str, image: QLabel, info: QLabel) -> QWidget:
        box = QWidget()
        col = QVBoxLayout(box)
        col.setContentsMargins(0, 0, 0, 0)
        heading = QLabel(title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(heading)
        col.addWidget(image, 0, Qt.AlignmentFlag.AlignCenter)
        col.addWidget(info)
        return box

    # -- API -----------------------------------------------------------------------------------
    def set_default(self, path: Path | None) -> None:
        """First detected image; used unless the user picked a specific one."""
        self._default = path
        if self._chosen is None:
            self.file_label.setText(path.name if path else "No image to preview yet.")
            if path is None:
                self._clear()

    def show_file(self, path: Path | str) -> None:
        self._chosen = Path(path)
        self.refresh()

    def refresh(self) -> None:
        path = self._chosen or self._default
        if path is None:
            self.file_label.setText("Select images first.")
            return
        try:
            settings = self._settings_provider()
            settings.validate()
        except ValueError as exc:
            self.file_label.setText(str(exc))
            return
        self._token += 1
        self.file_label.setText(f"{path.name} — encoding preview…")
        self.preview_button.setEnabled(False)
        QThreadPool.globalInstance().start(_PreviewTask(self._token, path, settings, self._signals))

    # -- internals -------------------------------------------------------------------------------
    def _choose(self) -> None:
        start = str((self._chosen or self._default or Path.home()).parent)
        name, _ = QFileDialog.getOpenFileName(self, "Choose an image to preview", start,
                                              "Images (*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG)")
        if name:
            self.show_file(name)

    def _clear(self) -> None:
        for label in (self.original_image, self.webp_image):
            label.clear()
            label.setText("—")
        self.original_info.setText("")
        self.webp_info.setText("")

    @staticmethod
    def _pixmap(thumb: _Thumb) -> QPixmap:
        image = QImage(thumb.data, thumb.width, thumb.height, thumb.width * 4,
                       QImage.Format.Format_RGBA8888)
        return QPixmap.fromImage(image.copy())   # copy: QImage does not own `thumb.data`

    def _on_done(self, token: int, data: _PreviewData) -> None:
        if token != self._token:
            return   # an older request finished late
        self.preview_button.setEnabled(True)
        self.original_image.setPixmap(self._pixmap(data.original))
        self.webp_image.setPixmap(self._pixmap(data.webp))
        change = percent_reduction(data.original_bytes, data.webp_bytes)
        verdict = (f"{format_percent(change)} smaller" if change >= 0
                   else f"{format_percent(-change)} LARGER")
        self.original_info.setText(f"{data.original_dims[0]}×{data.original_dims[1]} px · "
                                   f"{format_size(data.original_bytes)}")
        self.webp_info.setText(f"{data.webp_dims[0]}×{data.webp_dims[1]} px · "
                               f"{format_size(data.webp_bytes)} · {verdict}")
        path = self._chosen or self._default
        self.file_label.setText(path.name if path else "")

    def _on_failed(self, token: int, message: str) -> None:
        if token != self._token:
            return
        self.preview_button.setEnabled(True)
        self.file_label.setText(f"Preview failed: {message}")
