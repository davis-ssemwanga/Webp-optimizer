"""Runs a conversion plan with a small thread pool. Pure Python (no Qt) so it is testable.

* Only ``workers * 2`` images are in flight at once -> memory stays bounded for huge batches.
* Supports pause / resume / cancel. Images already being encoded are allowed to finish.
"""
from __future__ import annotations

import dataclasses
import threading
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from core.compression import ConversionSettings
from core.converter import ConversionResult, Status, convert_item
from core.output_planner import PlannedItem
from utils.size_formatter import percent_reduction


@dataclass
class BatchStats:
    total: int = 0
    processed: int = 0
    converted: int = 0
    failed: int = 0
    skipped: int = 0
    larger: int = 0                # converted files that grew
    original_bytes: int = 0        # sizes of successfully converted sources
    output_bytes: int = 0          # sizes of the WebP files written

    @property
    def saved_bytes(self) -> int:
        return self.original_bytes - self.output_bytes

    @property
    def percent_saved(self) -> float:
        return percent_reduction(self.original_bytes, self.output_bytes)

    @property
    def fraction_done(self) -> float:
        return self.processed / self.total if self.total else 0.0

    def snapshot(self) -> "BatchStats":
        return dataclasses.replace(self)


@dataclass
class BatchReport:
    results: list[ConversionResult] = field(default_factory=list)
    stats: BatchStats = field(default_factory=BatchStats)
    settings: ConversionSettings = field(default_factory=ConversionSettings)
    output_dir: Path | None = None
    started_at: float = 0.0
    finished_at: float = 0.0
    cancelled: bool = False

    @property
    def duration(self) -> float:
        return max(0.0, self.finished_at - self.started_at)

    @property
    def not_processed(self) -> int:
        return self.stats.total - self.stats.processed


# on_progress(stats_snapshot, finished_result_or_None, name_of_image_just_started)
ProgressCallback = Callable[[BatchStats, "ConversionResult | None", str], None]


class BatchRunner:
    def __init__(self, plan: list[PlannedItem], settings: ConversionSettings,
                 output_dir: Path | None = None):
        settings.validate()
        self.plan = plan
        self.settings = settings
        self.output_dir = output_dir
        self._cancel = threading.Event()
        self._resume = threading.Event()
        self._resume.set()

    # -- controls (safe to call from any thread) --------------------------------------
    def pause(self) -> None:
        self._resume.clear()

    def resume(self) -> None:
        self._resume.set()

    def cancel(self) -> None:
        self._cancel.set()
        self._resume.set()

    @property
    def is_paused(self) -> bool:
        return not self._resume.is_set()

    # -- main loop ---------------------------------------------------------------------
    def run(self, on_progress: ProgressCallback | None = None) -> BatchReport:
        stats = BatchStats(total=len(self.plan))
        report = BatchReport(stats=stats, settings=self.settings, output_dir=self.output_dir,
                             started_at=time.time())
        notify = on_progress or (lambda *_: None)
        workers = self.settings.effective_workers()
        window = workers * 2
        iterator = iter(self.plan)
        exhausted = False
        pending: dict = {}

        with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="webp") as pool:
            while True:
                cancelled = self._cancel.is_set()
                can_submit = (not exhausted and not cancelled and self._resume.is_set()
                              and len(pending) < window)
                if can_submit:
                    item = next(iterator, None)
                    if item is None:
                        exhausted = True
                    else:
                        pending[pool.submit(convert_item, item, self.settings)] = item
                        notify(stats.snapshot(), None, item.source.name)
                    continue

                if not pending:
                    if exhausted or cancelled:
                        break
                    self._resume.wait(0.1)  # paused with nothing in flight
                    continue

                done, _ = wait(list(pending), timeout=0.1, return_when=FIRST_COMPLETED)
                for future in done:
                    pending.pop(future)
                    result = future.result()
                    self._record(stats, result)
                    report.results.append(result)
                    notify(stats.snapshot(), result, result.source.name)

        report.cancelled = self._cancel.is_set() and stats.processed < stats.total
        report.finished_at = time.time()
        return report

    @staticmethod
    def _record(stats: BatchStats, result: ConversionResult) -> None:
        stats.processed += 1
        if result.status is Status.CONVERTED:
            stats.converted += 1
            stats.original_bytes += result.original_size
            stats.output_bytes += result.output_size
            if result.larger:
                stats.larger += 1
        elif result.status is Status.SKIPPED:
            stats.skipped += 1
        else:
            stats.failed += 1
