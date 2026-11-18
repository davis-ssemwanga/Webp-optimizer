"""Conversion settings and size calculations (no image I/O here)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class ConflictPolicy(str, Enum):
    RENAME = "rename"       # keep both: "photo (1).webp"
    SKIP = "skip"           # leave the existing file alone
    OVERWRITE = "overwrite" # replace the existing .webp (never the original image)


LOSSY_NOTE = (
    "Lossy: much smaller files. May introduce slight, usually invisible quality loss. "
    "Best for photographs."
)
LOSSLESS_NOTE = (
    "Lossless: exact pixels are kept, so files are much bigger than lossy. For photos "
    "the WebP is often LARGER than the original JPEG. Use it only for logos, graphics "
    "and screenshots (PNG)."
)


@dataclass
class ConversionSettings:
    quality: int = 85                 # 1-100 (ignored in lossless mode)
    lossless: bool = False
    method: int = 4                   # 0 (fast) - 6 (slowest, smallest)
    resize_enabled: bool = False
    max_width: int = 1920
    max_height: int = 1080
    conflict_policy: ConflictPolicy = ConflictPolicy.RENAME
    recursive: bool = False
    skip_if_larger: bool = False      # don't write a WebP that is bigger than the original
    workers: int = 0                  # 0 = choose automatically

    def validate(self) -> None:
        if not 1 <= int(self.quality) <= 100:
            raise ValueError("Quality must be between 1 and 100.")
        if not 0 <= int(self.method) <= 6:
            raise ValueError("Compression effort must be between 0 and 6.")
        if self.resize_enabled and not (int(self.max_width) > 0 or int(self.max_height) > 0):
            raise ValueError("Resizing needs a maximum width and/or height greater than 0.")
        if int(self.workers) < 0:
            raise ValueError("Worker count cannot be negative.")

    def effective_workers(self) -> int:
        if self.workers and self.workers > 0:
            return int(self.workers)
        return max(1, min(4, os.cpu_count() or 1))


def compute_target_size(width: int, height: int, max_width: int | None,
                        max_height: int | None) -> tuple[int, int]:
    """Fit inside max_width x max_height, keep aspect ratio, never upscale.

    A limit of 0/None means "no limit" for that axis.
    """
    scale = 1.0
    if max_width and max_width > 0:
        scale = min(scale, max_width / width)
    if max_height and max_height > 0:
        scale = min(scale, max_height / height)
    if scale >= 1.0:
        return width, height
    return max(1, round(width * scale)), max(1, round(height * scale))
