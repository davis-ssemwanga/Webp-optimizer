"""Validation of image files by extension AND real content."""
from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, UnidentifiedImageError

SUPPORTED_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})
# MPO is what Pillow reports for some camera JPEGs (multi-picture JPEG).
SUPPORTED_FORMATS = frozenset({"JPEG", "MPO", "PNG"})


class InvalidImageError(Exception):
    """The file is not a usable JPEG/PNG image."""


def has_supported_extension(path: str | os.PathLike) -> bool:
    return os.path.splitext(os.fspath(path))[1].lower() in SUPPORTED_EXTENSIONS


def check_format(img: Image.Image) -> None:
    """Raise if the decoded content is not JPEG/PNG, whatever the extension says."""
    if img.format not in SUPPORTED_FORMATS:
        found = img.format or "unknown"
        raise InvalidImageError(f"File content is {found}, not JPEG or PNG")


def validate_image(path: str | os.PathLike) -> None:
    """Open and integrity-check an image. Raises on any problem."""
    with Image.open(Path(path)) as img:
        check_format(img)
        img.verify()


def describe_error(exc: BaseException) -> str:
    """Turn an exception into a short, user-friendly message."""
    if isinstance(exc, InvalidImageError):
        return str(exc)
    if isinstance(exc, UnidentifiedImageError):
        return "Not a valid image (unrecognised format or corrupted file)"
    if isinstance(exc, Image.DecompressionBombError):
        return "Image is too large to process safely (decompression-bomb protection)"
    if isinstance(exc, PermissionError):
        return "Permission denied"
    if isinstance(exc, FileNotFoundError):
        return "File not found"
    if isinstance(exc, MemoryError):
        return "Not enough memory to process this image"
    if isinstance(exc, OSError):
        return f"Image is corrupted, truncated or could not be written ({exc})"
    return f"{type(exc).__name__}: {exc}"
