"""The image conversion engine: JPG/JPEG/PNG -> WebP.

``encode_webp`` does all image work in memory (also used by the preview panel);
``convert_item`` adds validation of paths, safe atomic writing and error capture.
"""
from __future__ import annotations

import io
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from PIL import Image, ImageOps

from core.compression import ConversionSettings, compute_target_size
from core.image_validator import InvalidImageError, check_format, describe_error
from core.output_planner import PlanAction, PlannedItem
from utils.file_utils import atomic_write_bytes, real_key
from utils.size_formatter import format_size, percent_reduction

try:  # LittleCMS is bundled with Pillow wheels, but stay defensive.
    from PIL import ImageCms
except ImportError:  # pragma: no cover
    ImageCms = None

log = logging.getLogger(__name__)

WEBP_MAX_DIMENSION = 16383  # hard limit of the WebP format
_HIGH_BIT_MODES = {"I", "I;16", "I;16L", "I;16B", "I;16N"}


class Status(str, Enum):
    CONVERTED = "converted"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class EncodeResult:
    data: bytes
    source_size: tuple[int, int]   # dimensions after EXIF orientation, before resizing
    output_size: tuple[int, int]
    has_alpha: bool
    icc_preserved: bool


@dataclass
class ConversionResult:
    source: Path
    dest: Path | None
    status: Status
    original_size: int = 0                       # bytes
    output_size: int = 0                         # bytes
    original_dims: tuple[int, int] | None = None
    output_dims: tuple[int, int] | None = None
    message: str = ""
    larger: bool = False                         # WebP is bigger than the original
    seconds: float = 0.0

    @property
    def reduction_percent(self) -> float:
        if self.status is not Status.CONVERTED:
            return 0.0
        return percent_reduction(self.original_size, self.output_size)


# --------------------------------------------------------------------------- encoding
def _icc_color_space(icc: bytes | None) -> str | None:
    """Colour space signature stored in bytes 16-20 of an ICC header ('RGB', 'GRAY', 'CMYK')."""
    if not icc or len(icc) < 20:
        return None
    return icc[16:20].decode("ascii", "replace").strip()


def _cmyk_to_rgb(img: Image.Image, icc: bytes | None) -> Image.Image:
    if icc and ImageCms is not None and _icc_color_space(icc) == "CMYK":
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            dst = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))
            return ImageCms.profileToProfile(img, src, dst, outputMode="RGB")
        except Exception as exc:  # fall back to Pillow's naive conversion
            log.warning("CMYK profile conversion failed (%s); using plain conversion", exc)
    return img.convert("RGB")


def _high_bit_to_gray(img: Image.Image) -> Image.Image:
    try:
        return img.point(lambda v: v * (1 / 256)).convert("L")
    except Exception:  # pragma: no cover - extremely unusual modes
        return img.convert("L")


def _normalise_mode(img: Image.Image, icc: bytes | None) -> tuple[Image.Image, bytes | None]:
    """Bring any Pillow mode to RGB or RGBA (what WebP stores) and fix the ICC profile."""
    mode = img.mode
    if mode == "CMYK":
        return _cmyk_to_rgb(img, icc), None  # result is sRGB; the CMYK profile no longer applies

    if mode in _HIGH_BIT_MODES:
        img = _high_bit_to_gray(img)
        mode = img.mode

    if mode not in ("RGB", "RGBA"):
        has_alpha = "A" in img.getbands() or "transparency" in img.info
        img = img.convert("RGBA" if has_alpha else "RGB")
    elif mode == "RGB" and "transparency" in img.info:  # PNG colour-key transparency
        img = img.convert("RGBA")

    # A grey or CMYK profile must not be attached to RGB pixel data.
    if icc and _icc_color_space(icc) != "RGB":
        icc = None
    return img, icc


def encode_webp(src: Path, settings: ConversionSettings) -> EncodeResult:
    """Decode ``src`` and return WebP bytes. Never touches the file on disk."""
    settings.validate()
    with Image.open(src) as img:
        check_format(img)
        img.load()                                  # surfaces truncated/corrupt data now
        icc = img.info.get("icc_profile")

        # Apply camera rotation. exif_transpose copies the pixels, so skip it (and the
        # extra memory) when the image has no rotation to apply.
        if img.getexif().get(0x0112, 1) in (0, 1):
            work = img
        else:
            work = ImageOps.exif_transpose(img)

        work, icc = _normalise_mode(work, icc)
        oriented_size = work.size

        if settings.resize_enabled:
            target = compute_target_size(*work.size, settings.max_width, settings.max_height)
            if target != work.size:
                work = work.resize(target, Image.Resampling.LANCZOS)

        if max(work.size) > WEBP_MAX_DIMENSION:
            raise InvalidImageError(
                f"Image is {work.size[0]}x{work.size[1]} px; WebP supports at most "
                f"{WEBP_MAX_DIMENSION} px per side. Enable resizing to convert it."
            )

        params: dict = {
            "format": "WEBP",
            "lossless": settings.lossless,
            # In lossless mode Pillow uses "quality" as an effort/size trade-off; 100 = smallest.
            "quality": 100 if settings.lossless else int(settings.quality),
            "method": int(settings.method),
        }
        if icc:
            params["icc_profile"] = icc

        buffer = io.BytesIO()
        work.save(buffer, **params)
        return EncodeResult(
            data=buffer.getvalue(),
            source_size=oriented_size,
            output_size=work.size,
            has_alpha="A" in work.getbands(),
            icc_preserved=bool(icc),
        )


# ---------------------------------------------------------------------- file conversion
def _guard_paths(src: Path, dest: Path) -> None:
    if dest.suffix.lower() != ".webp":
        raise ValueError("Refusing to write a non-.webp output file")
    if real_key(src) == real_key(dest):
        raise ValueError("Refusing to write over the source image")


def convert_item(item: PlannedItem, settings: ConversionSettings) -> ConversionResult:
    """Convert one planned item. Never raises: problems are returned as FAILED results."""
    started = time.perf_counter()
    src, dest = item.source, item.dest

    def finish(**kwargs) -> ConversionResult:
        return ConversionResult(source=src, dest=dest, seconds=time.perf_counter() - started, **kwargs)

    try:
        original_size = src.stat().st_size
    except OSError as exc:
        return finish(status=Status.FAILED, message=describe_error(exc))

    if item.action is PlanAction.SKIP:
        return finish(status=Status.SKIPPED, original_size=original_size,
                      message="Output file already exists (skipped)")
    try:
        _guard_paths(src, dest)
        encoded = encode_webp(src, settings)
        if settings.skip_if_larger and len(encoded.data) > original_size:
            return finish(
                status=Status.SKIPPED, original_size=original_size,
                message=f"Not saved: WebP would be larger ({format_size(original_size)} -> "
                        f"{format_size(len(encoded.data))})")
        atomic_write_bytes(dest, encoded.data)
    except Exception as exc:  # noqa: BLE001 - one bad image must never stop the batch
        log.debug("Conversion failed for %s", src, exc_info=True)
        return finish(status=Status.FAILED, original_size=original_size, message=describe_error(exc))

    out_bytes = len(encoded.data)
    notes = []
    if item.action is PlanAction.OVERWRITE:
        notes.append("Replaced existing .webp")
    larger = out_bytes > original_size
    if larger:
        notes.append("WebP is larger than the original")
    return finish(
        status=Status.CONVERTED,
        original_size=original_size,
        output_size=out_bytes,
        original_dims=encoded.source_size,
        output_dims=encoded.output_size,
        larger=larger,
        message="; ".join(notes),
    )
