"""CSV and TXT conversion reports."""
from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path

from core.batch_runner import BatchReport
from core.converter import ConversionResult, Status
from utils.size_formatter import format_duration, format_percent, format_size

CSV_COLUMNS = [
    "source", "output", "status", "original_bytes", "output_bytes", "reduction_percent",
    "original_width", "original_height", "output_width", "output_height",
    "larger_than_original", "message",
]


def _safe_cell(value: object) -> object:
    """Stop spreadsheet apps from treating file names like '=cmd()' as formulas."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@"):
        return "'" + value
    return value


def _row(r: ConversionResult) -> list:
    ow, oh = r.original_dims or ("", "")
    nw, nh = r.output_dims or ("", "")
    converted = r.status is Status.CONVERTED
    return [
        _safe_cell(str(r.source)), _safe_cell(str(r.dest) if r.dest else ""), r.status.value,
        r.original_size, r.output_size if converted else "",
        f"{r.reduction_percent:.2f}" if converted else "",
        ow, oh, nw, nh, "yes" if r.larger else "no", _safe_cell(r.message),
    ]


def write_csv(report: BatchReport, path: Path | str) -> None:
    # utf-8-sig so Excel opens non-ASCII file names correctly.
    with open(path, "w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for result in report.results:
            writer.writerow(_row(result))


def build_text(report: BatchReport) -> str:
    s, cfg = report.stats, report.settings
    started = datetime.fromtimestamp(report.started_at).strftime("%Y-%m-%d %H:%M:%S")
    mode = "Lossless" if cfg.lossless else f"Lossy, quality {cfg.quality}"
    resize = f"max {cfg.max_width}x{cfg.max_height} px (no upscaling)" if cfg.resize_enabled else "off (original dimensions)"
    lines = [
        "WebP Optimizer - Conversion Report",
        "=" * 40,
        f"Started:            {started}",
        f"Duration:           {format_duration(report.duration)}",
        f"Output folder:      {report.output_dir or '-'}",
        f"Status:             {'CANCELLED - ' + str(report.not_processed) + ' image(s) not processed' if report.cancelled else 'Completed'}",
        "",
        "Settings",
        "-" * 40,
        f"Mode:               {mode}",
        f"Compression effort: {cfg.method}",
        f"Resize:             {resize}",
        f"If file exists:     {cfg.conflict_policy.value}",
        f"Recursive scan:     {'yes' if cfg.recursive else 'no'}",
        "",
        "Totals",
        "-" * 40,
        f"Images detected:    {s.total}",
        f"Converted:          {s.converted}",
        f"Failed:             {s.failed}",
        f"Skipped:            {s.skipped}",
        f"Original size:      {format_size(s.original_bytes)}",
        f"WebP size:          {format_size(s.output_bytes)}",
        f"Space saved:        {format_size(s.saved_bytes)} ({format_percent(s.percent_saved)})",
    ]
    if s.larger:
        lines.append(f"NOTE: {s.larger} image(s) became LARGER as WebP (listed below).")

    larger = [r for r in report.results if r.larger]
    failed = [r for r in report.results if r.status is Status.FAILED]
    if larger:
        lines += ["", "Images that grew", "-" * 40]
        lines += [f"{r.source}: {format_size(r.original_size)} -> {format_size(r.output_size)}"
                  f" ({format_percent(r.reduction_percent)})" for r in larger]
    if failed:
        lines += ["", "Failed images", "-" * 40]
        lines += [f"{r.source}: {r.message}" for r in failed]
    return "\n".join(lines) + "\n"


def write_text(report: BatchReport, path: Path | str) -> None:
    Path(path).write_text(build_text(report), encoding="utf-8")
