"""Find supported images in files and folders."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from core.image_validator import has_supported_extension
from utils.file_utils import real_key


@dataclass(frozen=True)
class SourceItem:
    path: Path
    rel_dir: Path = Path(".")   # sub-folder (relative to the chosen folder) to mirror in the output


@dataclass
class ScanResult:
    items: list[SourceItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def scan_sources(paths: Iterable[str | os.PathLike], recursive: bool = False,
                 exclude_dirs: Iterable[str | os.PathLike] = ()) -> ScanResult:
    """Collect supported images from a mix of files and folders.

    * Extensions are checked here (cheap); real content is validated at conversion time.
    * ``exclude_dirs`` (typically the output folder) is never descended into, so a
      converted folder inside the source tree is not scanned again.
    * Symlinked folders are not followed, which avoids infinite loops.
    """
    excluded = {real_key(p) for p in exclude_dirs if str(p)}
    result = ScanResult()
    seen: set[str] = set()

    def add(file_path: Path, rel_dir: Path) -> None:
        key = real_key(file_path)
        if key not in seen:
            seen.add(key)
            result.items.append(SourceItem(file_path, rel_dir))

    for raw in paths:
        src = Path(raw)
        try:
            if src.is_file():
                if has_supported_extension(src):
                    add(src, Path("."))
            elif src.is_dir():
                _scan_dir(src, recursive, excluded, add, result.errors)
            else:
                result.errors.append(f"Not found: {src}")
        except OSError as exc:
            result.errors.append(f"Cannot access {src}: {exc.strerror or exc}")

    result.items.sort(key=lambda i: (str(i.rel_dir).casefold(), i.path.name.casefold()))
    return result


def _scan_dir(root: Path, recursive: bool, excluded: set[str], add, errors: list[str]) -> None:
    stack = [root]
    while stack:
        current = stack.pop()
        if real_key(current) in excluded:
            continue
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError as exc:
            errors.append(f"Cannot read folder {current}: {exc.strerror or exc}")
            continue
        rel = current.relative_to(root)
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    if recursive:
                        stack.append(Path(entry.path))
                elif has_supported_extension(entry.name) and entry.is_file():
                    add(Path(entry.path), rel)
            except OSError as exc:
                errors.append(f"Cannot read {entry.path}: {exc.strerror or exc}")
