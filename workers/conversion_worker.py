"""QThread wrapper around core.batch_runner.BatchRunner.

GUI updates are throttled: results are buffered and emitted at most ~10 times a second,
so converting thousands of tiny images does not flood the event loop.
"""
from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from core.batch_runner import BatchRunner, BatchStats
from core.compression import ConversionSettings
from core.converter import ConversionResult
from core.output_planner import PlannedItem

_EMIT_INTERVAL = 0.1  # seconds


class ConversionWorker(QThread):
    # stats snapshot, name of the image most recently started, list[ConversionResult] since last emit
    progress = Signal(object, str, object)
    completed = Signal(object)      # BatchReport
    crashed = Signal(str)           # unexpected internal error

    def __init__(self, plan: list[PlannedItem], settings: ConversionSettings,
                 output_dir: Path, parent=None):
        super().__init__(parent)
        self._runner = BatchRunner(plan, settings, output_dir)
        self._buffer: list[ConversionResult] = []
        self._last_emit = 0.0
        self._last_stats: BatchStats | None = None
        self._current = ""

    # -- controls, called from the GUI thread ------------------------------------------
    def pause(self) -> None:
        self._runner.pause()

    def resume(self) -> None:
        self._runner.resume()

    def cancel(self) -> None:
        self._runner.cancel()

    # -- thread body ---------------------------------------------------------------------
    def run(self) -> None:
        try:
            report = self._runner.run(self._on_progress)
            self._flush()
            self.completed.emit(report)
        except Exception as exc:  # noqa: BLE001
            self.crashed.emit(f"{type(exc).__name__}: {exc}")

    def _on_progress(self, stats: BatchStats, result: ConversionResult | None, name: str) -> None:
        self._last_stats = stats
        self._current = name
        if result is not None:
            self._buffer.append(result)
        now = time.monotonic()
        if now - self._last_emit >= _EMIT_INTERVAL:
            self._flush()

    def _flush(self) -> None:
        if self._last_stats is None:
            return
        batch, self._buffer = self._buffer, []
        self._last_emit = time.monotonic()
        self.progress.emit(self._last_stats, self._current, batch)
