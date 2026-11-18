"""Decide where every converted file goes, and make sure nothing can be lost.

Rules enforced here:
* Output is ``<name>.webp`` with the original stem (sanitised for the filesystem).
* Two sources that would produce the same name (``photo.jpg`` + ``photo.png``) are
  NEVER allowed to overwrite each other, whatever the conflict policy is.
  The second becomes ``photo_png.webp`` (then ``photo_png (1).webp`` ...).
* Files that already exist on disk follow the chosen policy: rename / skip / overwrite.
* The output folder may not be the source folder itself.
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Iterable

from core.compression import ConflictPolicy
from core.folder_scanner import SourceItem
from utils.file_utils import path_key, real_key, sanitize_stem


class PlanAction(str, Enum):
    CONVERT = "convert"
    OVERWRITE = "overwrite"   # convert and replace an existing .webp
    SKIP = "skip"             # do nothing, an output already exists


@dataclass(frozen=True)
class PlannedItem:
    source: Path
    dest: Path
    action: PlanAction = PlanAction.CONVERT


def default_output_dir(sources: list[Path]) -> Path | None:
    """``D:/Website/Gallery`` -> ``D:/Website/Gallery_Converted_WebP``.

    For individually selected files the output goes to ``<their folder>/Converted_WebP``.
    """
    if not sources:
        return None
    first = Path(sources[0])
    if first.is_dir():
        if not first.name:  # drive root such as "D:/"
            return first / "Converted_WebP"
        return first.with_name(f"{first.name}_Converted_WebP")
    return first.parent / "Converted_WebP"


def validate_job(sources: Iterable[Path], out_dir: Path | str) -> list[str]:
    """Return a list of human-readable problems (empty list = OK)."""
    errors: list[str] = []
    sources = [Path(s) for s in sources]
    if not sources:
        errors.append("No images or folder selected.")
    if not str(out_dir).strip():
        errors.append("No output folder chosen.")
        return errors
    out_dir = Path(out_dir)
    if out_dir.exists() and not out_dir.is_dir():
        errors.append(f"The output path exists but is not a folder:\n{out_dir}")
    for src in sources:
        if not src.exists():
            errors.append(f"Source no longer exists:\n{src}")
        elif src.is_dir() and real_key(src) == real_key(out_dir):
            errors.append(
                "The output folder must be different from the source folder, so original "
                f"images are never mixed with converted ones:\n{src}"
            )
    return errors


def prepare_output_dir(out_dir: Path) -> str | None:
    """Create the output folder if needed and check it is writable. Returns an error or None."""
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryFile(dir=out_dir):
            pass
    except PermissionError:
        return f"Permission denied: cannot write to\n{out_dir}"
    except OSError as exc:
        return f"Cannot use output folder\n{out_dir}\n({exc.strerror or exc})"
    return None


def plan_outputs(items: list[SourceItem], out_dir: Path,
                 policy: ConflictPolicy = ConflictPolicy.RENAME) -> list[PlannedItem]:
    out_dir = Path(out_dir)
    claimed: set[str] = set()
    plan: list[PlannedItem] = []

    for item in items:
        base_dir = out_dir / item.rel_dir
        stem = sanitize_stem(item.path.stem)
        dest = base_dir / f"{stem}.webp"

        if path_key(dest) in claimed:
            # Same name produced by another source in this batch (e.g. a.jpg + a.png).
            ext = item.path.suffix.lstrip(".").lower() or "img"
            dest = base_dir / f"{stem}_{ext}.webp"

        dest, action = _claim(dest, claimed, policy)
        plan.append(PlannedItem(item.path, dest, action))
    return plan


def _claim(dest: Path, claimed: set[str], policy: ConflictPolicy) -> tuple[Path, PlanAction]:
    candidate = dest
    n = 0
    while path_key(candidate) in claimed or (policy is ConflictPolicy.RENAME and candidate.exists()):
        n += 1
        candidate = dest.with_name(f"{dest.stem} ({n}){dest.suffix}")
    claimed.add(path_key(candidate))

    if candidate.exists():  # only reachable for SKIP / OVERWRITE
        return candidate, (PlanAction.SKIP if policy is ConflictPolicy.SKIP else PlanAction.OVERWRITE)
    return candidate, PlanAction.CONVERT
