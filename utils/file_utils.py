"""Filesystem helpers: filename sanitising, atomic writes, path keys."""
from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def sanitize_stem(stem: str, max_length: int = 180) -> str:
    """Make a filename stem safe on Windows/macOS/Linux (keeps Unicode letters)."""
    cleaned = _INVALID_CHARS.sub("_", stem).strip().rstrip(". ")
    if not cleaned:
        cleaned = "image"
    if cleaned.split(".")[0].upper() in _RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned[:max_length].rstrip(". ") or "image"


def path_key(path: str | os.PathLike) -> str:
    """Case-insensitive, normalised key used to detect filename collisions."""
    return os.path.normpath(os.fspath(path)).casefold()


def real_key(path: str | os.PathLike) -> str:
    """Key for comparing two paths that may be spelled differently (symlinks, case)."""
    return os.path.normcase(os.path.realpath(path))


def atomic_write_bytes(dest: Path, data: bytes) -> None:
    """Write ``data`` to a temp file next to ``dest`` and atomically move it into place.

    A crash or cancellation can therefore never leave a half-written .webp behind.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".webp_", suffix=".tmp", dir=dest.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp_name, dest)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def resource_path(relative: str) -> Path:
    """Locate bundled resources both from source and from a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root / relative
