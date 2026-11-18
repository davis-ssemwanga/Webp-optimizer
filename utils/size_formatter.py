"""Human-readable formatting helpers for sizes, percentages and durations."""
from __future__ import annotations


def format_size(num_bytes: float) -> str:
    """Return a size such as ``812 B``, ``4.20 KB`` or ``1.35 GB`` (1 KB = 1024 B)."""
    value = float(num_bytes)
    sign = "-" if value < 0 else ""
    value = abs(value)
    if value < 1024:
        return f"{sign}{int(value)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        value /= 1024
        if value < 1024 or unit == "TB":
            return f"{sign}{value:.2f} {unit}"
    return f"{sign}{value:.2f} TB"  # pragma: no cover


def percent_reduction(original: int | float, new: int | float) -> float:
    """Percentage saved. Positive = smaller, negative = larger than the original."""
    if original <= 0:
        return 0.0
    return (original - new) / original * 100.0


def format_percent(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}%"


def format_duration(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f} s"
    minutes, secs = divmod(int(round(seconds)), 60)
    if minutes < 60:
        return f"{minutes} min {secs:02d} s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} h {minutes:02d} min {secs:02d} s"
