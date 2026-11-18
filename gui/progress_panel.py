"""Section 4 (progress dashboard) and Section 5 (completion summary)."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QAbstractItemView, QGridLayout, QGroupBox, QHBoxLayout, QHeaderView,
                               QLabel, QProgressBar, QPushButton, QTableWidget, QTableWidgetItem,
                               QVBoxLayout)

from core.batch_runner import BatchReport, BatchStats
from core.converter import ConversionResult, Status
from utils.size_formatter import format_duration, format_percent, format_size

MAX_TABLE_ROWS = 5000
_RED, _AMBER, _GREY = QColor("#b42318"), QColor("#b54708"), QColor("#627d98")


class ProgressPanel(QGroupBox):
    row_selected = Signal(str)   # path of the clicked image

    def __init__(self, parent=None):
        super().__init__("4. Progress", parent)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1)
        self.current_label = QLabel("Idle")
        self.counts_label = QLabel("")
        self.sizes_label = QLabel("")
        self.sizes_label.setObjectName("hint")

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["File", "Original", "WebP", "Change", "Status"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setMinimumHeight(300)   # always room for ~9 rows
        self.table_note = QLabel("")
        self.table_note.setObjectName("hint")
        self.table.cellClicked.connect(self._cell_clicked)

        layout = QVBoxLayout(self)
        layout.addWidget(self.bar)
        layout.addWidget(self.current_label)
        layout.addWidget(self.counts_label)
        layout.addWidget(self.sizes_label)
        layout.addWidget(self.table, 1)
        layout.addWidget(self.table_note)

    def reset(self, total: int = 0) -> None:
        self.table.setRowCount(0)
        self.table_note.setText("")
        self.bar.setRange(0, max(total, 1))
        self.bar.setValue(0)
        self.bar.setFormat("%p%")
        self.current_label.setText("Starting…" if total else "Idle")
        self.counts_label.setText(f"Total: {total}   Converted: 0   Failed: 0   Skipped: 0")
        self.sizes_label.setText("")

    def update_progress(self, stats: BatchStats, current: str, results: list[ConversionResult]) -> None:
        self.bar.setRange(0, max(stats.total, 1))
        self.bar.setValue(stats.processed)
        if current and stats.processed < stats.total:
            self.current_label.setText(f"Processing: {current}")
        self.counts_label.setText(
            f"Total: {stats.total}   Converted: {stats.converted}   "
            f"Failed: {stats.failed}   Skipped: {stats.skipped}"
        )
        self.sizes_label.setText(
            f"Original {format_size(stats.original_bytes)}  →  WebP {format_size(stats.output_bytes)}   "
            f"Saved {format_size(stats.saved_bytes)} ({format_percent(stats.percent_saved)})"
            + (f"   ⚠ {stats.larger} grew larger" if stats.larger else "")
        )
        self._append(results)

    def set_status(self, text: str) -> None:
        self.current_label.setText(text)

    # -- table -----------------------------------------------------------------------------
    def _append(self, results: list[ConversionResult]) -> None:
        room = MAX_TABLE_ROWS - self.table.rowCount()
        if room <= 0:
            self.table_note.setText(f"Showing the first {MAX_TABLE_ROWS} results. "
                                    "Export the report to see all of them.")
            return
        batch = results[:room]
        if len(results) > room:
            self.table_note.setText(f"Showing the first {MAX_TABLE_ROWS} results. "
                                    "Export the report to see all of them.")
        self.table.setUpdatesEnabled(False)
        try:
            for result in batch:
                self._add_row(result)
        finally:
            self.table.setUpdatesEnabled(True)
        if batch:
            self.table.scrollToBottom()

    def _add_row(self, r: ConversionResult) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        if r.status is Status.CONVERTED:
            change = (f"+{format_percent(-r.reduction_percent)}" if r.larger
                      else f"-{format_percent(r.reduction_percent)}")
            cells = [r.source.name, format_size(r.original_size), format_size(r.output_size), change,
                     r.message or "Converted"]
            color = _AMBER if r.larger else None
        elif r.status is Status.SKIPPED:
            cells = [r.source.name, format_size(r.original_size), "—", "—", r.message]
            color = _GREY
        else:
            cells = [r.source.name, format_size(r.original_size) if r.original_size else "—", "—", "—",
                     f"Failed: {r.message}"]
            color = _RED
        for col, text in enumerate(cells):
            item = QTableWidgetItem(text)
            item.setToolTip(str(r.source) if col == 0 else text)
            if col == 0:
                item.setData(Qt.ItemDataRole.UserRole, str(r.source))
            if color is not None:
                item.setForeground(QBrush(color))
            self.table.setItem(row, col, item)

    def _cell_clicked(self, row: int, _col: int) -> None:
        item = self.table.item(row, 0)
        if item is not None:
            path = item.data(Qt.ItemDataRole.UserRole)
            if path:
                self.row_selected.emit(path)


class SummaryPanel(QGroupBox):
    open_requested = Signal()
    export_requested = Signal()

    def __init__(self, parent=None):
        super().__init__("5. Summary", parent)
        self.headline = QLabel("Results will appear here when a conversion finishes.")
        self.headline.setWordWrap(True)
        self.values: dict[str, QLabel] = {}
        grid = QGridLayout()
        names = ["Images processed", "Converted", "Failed", "Skipped",
                 "Original size", "WebP size", "Space saved", "Compression", "Time taken"]
        for i, name in enumerate(names):
            label = QLabel(name + ":")
            label.setObjectName("hint")
            value = QLabel("—")
            value.setStyleSheet("font-weight: 600;")
            self.values[name] = value
            grid.addWidget(label, i // 3, (i % 3) * 2)
            grid.addWidget(value, i // 3, (i % 3) * 2 + 1)
        self.open_button = QPushButton("Open Output Folder")
        self.export_button = QPushButton("Export Report…")
        self.open_button.setEnabled(False)
        self.export_button.setEnabled(False)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.open_button)
        buttons.addWidget(self.export_button)

        layout = QVBoxLayout(self)
        layout.addWidget(self.headline)
        layout.addLayout(grid)
        layout.addLayout(buttons)
        self.open_button.clicked.connect(self.open_requested)
        self.export_button.clicked.connect(self.export_requested)

    def reset(self) -> None:
        self.headline.setText("Results will appear here when a conversion finishes.")
        for value in self.values.values():
            value.setText("—")
        self.open_button.setEnabled(False)
        self.export_button.setEnabled(False)

    def show_report(self, report: BatchReport) -> None:
        s = report.stats
        if report.cancelled:
            self.headline.setText(f"Cancelled — {report.not_processed} image(s) were not processed. "
                                  "The finished files are safe in the output folder.")
        elif s.failed:
            self.headline.setText(f"Finished with {s.failed} failed image(s). See the list above for the reasons.")
        else:
            self.headline.setText("Finished successfully.")
        if s.larger:
            self.headline.setText(self.headline.text() +
                                  f"\n{s.larger} image(s) became larger as WebP (shown in orange).")
        v = self.values
        v["Images processed"].setText(f"{s.processed} of {s.total}")
        v["Converted"].setText(str(s.converted))
        v["Failed"].setText(str(s.failed))
        v["Skipped"].setText(str(s.skipped))
        v["Original size"].setText(format_size(s.original_bytes))
        v["WebP size"].setText(format_size(s.output_bytes))
        v["Space saved"].setText(format_size(s.saved_bytes))
        v["Compression"].setText(format_percent(s.percent_saved))
        v["Time taken"].setText(format_duration(report.duration))
        self.open_button.setEnabled(report.output_dir is not None)
        self.export_button.setEnabled(True)
