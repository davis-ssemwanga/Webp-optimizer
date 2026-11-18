"""Main window: wires the panels to the core engine and the background worker."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QFileDialog, QGroupBox, QHBoxLayout, QMainWindow,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from core.batch_runner import BatchReport
from core.compression import ConflictPolicy
from core.folder_scanner import SourceItem, scan_sources
from core.output_planner import (PlanAction, default_output_dir, plan_outputs, prepare_output_dir,
                                 validate_job)
from core.report_generator import write_csv, write_text
from gui.preview_panel import PreviewPanel
from gui.progress_panel import ProgressPanel, SummaryPanel
from gui.settings_panel import SettingsPanel
from gui.source_panel import SourcePanel
from gui.styles import APP_STYLE
from utils.file_utils import resource_path
from workers.conversion_worker import ConversionWorker

APP_TITLE = "WebP Optimizer: Batch JPG/PNG → WebP"


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1260, 880)
        self.setAcceptDrops(True)
        self.setStyleSheet(APP_STYLE)
        icon = resource_path("assets/icons/app.ico")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
            QApplication.setWindowIcon(QIcon(str(icon)))

        self.sources: list[Path] = []
        self.items: list[SourceItem] = []
        self.worker: ConversionWorker | None = None
        self.last_report: BatchReport | None = None

        self._build_ui()
        self._connect()
        self._update_buttons()
        self.statusBar().showMessage("Ready. Select images or a folder to begin.")

    # ------------------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        self.source_panel = SourcePanel()
        self.settings_panel = SettingsPanel()
        self.preview_panel = PreviewPanel(self.settings_panel.read_settings)
        self.progress_panel = ProgressPanel()
        self.summary_panel = SummaryPanel()

        self.start_button = QPushButton("Start Conversion")
        self.start_button.setObjectName("primary")
        self.pause_button = QPushButton("Pause")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("danger")
        self.clear_button = QPushButton("Clear Selection")
        controls_box = QGroupBox("3. Controls")
        grid = QVBoxLayout(controls_box)
        top, bottom = QHBoxLayout(), QHBoxLayout()
        top.addWidget(self.start_button, 1)
        bottom.addWidget(self.pause_button)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.clear_button)
        grid.addLayout(top)
        grid.addLayout(bottom)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.source_panel)
        left_layout.addWidget(self.settings_panel)
        left_layout.addWidget(controls_box)
        left_layout.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(580)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.preview_panel)
        right_layout.addWidget(self.progress_panel, 1)
        right_layout.addWidget(self.summary_panel)

        central = QWidget()
        root = QHBoxLayout(central)
        root.addWidget(scroll)
        right_scroll = QScrollArea()
        right_scroll.setWidget(right)
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(right_scroll, 1)
        self.setCentralWidget(central)

    def _connect(self) -> None:
        self.source_panel.selection_changed.connect(self._on_sources_changed)
        self.settings_panel.recursive_toggled.connect(lambda _on: self._rescan())
        self.progress_panel.row_selected.connect(self.preview_panel.show_file)
        self.summary_panel.open_requested.connect(self._open_output)
        self.summary_panel.export_requested.connect(self._export_report)
        self.start_button.clicked.connect(self.start_conversion)
        self.pause_button.clicked.connect(self._toggle_pause)
        self.cancel_button.clicked.connect(self._cancel)
        self.clear_button.clicked.connect(self.clear_selection)

    # ---------------------------------------------------------------- drag and drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self.worker is None and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths and self.worker is None:
            self.source_panel.set_paths(paths)
            event.acceptProposedAction()

    # ----------------------------------------------------------- selection handling
    def _on_sources_changed(self, paths: list) -> None:
        self.sources = [Path(p) for p in paths]
        if not self.settings_panel.output_user_edited:
            self.settings_panel.set_output_dir(default_output_dir(self.sources))
        self.progress_panel.reset(0)
        self.summary_panel.reset()
        self.last_report = None
        self._rescan()

    def _output_path(self) -> Path | None:
        text = self.settings_panel.output_dir_text()
        return Path(text).expanduser() if text else None

    def _rescan(self) -> None:
        if not self.sources:
            self.items = []
            self.source_panel.show_summary([], 0, [])
            self.preview_panel.set_default(None)
            self._update_buttons()
            return
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            out = self._output_path()
            result = scan_sources(self.sources, self.settings_panel.recursive(),
                                  exclude_dirs=[out] if out else [])
        finally:
            QApplication.restoreOverrideCursor()
        self.items = result.items
        self.source_panel.show_summary(self.sources, len(self.items), result.errors)
        self.preview_panel.set_default(self.items[0].path if self.items else None)
        self.statusBar().showMessage(f"{len(self.items)} image(s) detected.")
        self._update_buttons()

    def clear_selection(self) -> None:
        if self.worker is not None:
            return
        self.sources, self.items, self.last_report = [], [], None
        self.source_panel.clear()
        self.settings_panel.reset_output()
        self.preview_panel.set_default(None)
        self.progress_panel.reset(0)
        self.summary_panel.reset()
        self.statusBar().showMessage("Selection cleared.")
        self._update_buttons()

    # ------------------------------------------------------------------ conversion
    def start_conversion(self) -> None:
        if self.worker is not None:
            return
        settings = self.settings_panel.read_settings()
        try:
            settings.validate()
        except ValueError as exc:
            QMessageBox.warning(self, "Check your settings", str(exc))
            return

        out_dir = self._output_path()
        problems = validate_job(self.sources, out_dir or "")
        if problems:
            QMessageBox.warning(self, "Cannot start", "\n\n".join(problems))
            return

        # Re-scan now: the folder may have changed since it was selected.
        scan = scan_sources(self.sources, settings.recursive, exclude_dirs=[out_dir])
        if not scan.items:
            QMessageBox.information(self, "Nothing to convert",
                                    "No JPG, JPEG or PNG images were found in the selection.")
            return
        plan = plan_outputs(scan.items, out_dir, settings.conflict_policy)

        overwrites = sum(1 for p in plan if p.action is PlanAction.OVERWRITE)
        if overwrites and settings.conflict_policy is ConflictPolicy.OVERWRITE:
            answer = QMessageBox.question(
                self, "Replace existing files?",
                f"{overwrites} existing .webp file(s) in the output folder will be replaced.\n"
                "Your original images are not affected.\n\nContinue?")
            if answer != QMessageBox.StandardButton.Yes:
                return

        error = prepare_output_dir(out_dir)
        if error:
            QMessageBox.critical(self, "Output folder problem", error)
            return

        self.items = scan.items
        self.progress_panel.reset(len(plan))
        self.summary_panel.reset()
        self.last_report = None
        self.worker = ConversionWorker(plan, settings, out_dir, self)
        self.worker.progress.connect(self.progress_panel.update_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.crashed.connect(self._on_crashed)
        self.worker.finished.connect(self._on_thread_finished)
        self._set_running(True)
        self.statusBar().showMessage(f"Converting {len(plan)} image(s)…")
        self.worker.start()

    def _toggle_pause(self) -> None:
        if self.worker is None:
            return
        if self.pause_button.text() == "Pause":
            self.worker.pause()
            self.pause_button.setText("Resume")
            self.progress_panel.set_status("Paused (images already in progress will finish)")
            self.statusBar().showMessage("Paused.")
        else:
            self.worker.resume()
            self.pause_button.setText("Pause")
            self.statusBar().showMessage("Converting…")

    def _cancel(self) -> None:
        if self.worker is not None:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.pause_button.setEnabled(False)
            self.progress_panel.set_status("Cancelling… finishing images already in progress")

    def _on_completed(self, report: BatchReport) -> None:
        self.last_report = report
        self.summary_panel.show_report(report)
        self.progress_panel.set_status("Cancelled" if report.cancelled else "Done")
        s = report.stats
        self.statusBar().showMessage(
            f"{'Cancelled' if report.cancelled else 'Finished'}: {s.converted} converted, "
            f"{s.failed} failed, {s.skipped} skipped.")

    def _on_crashed(self, message: str) -> None:
        QMessageBox.critical(self, "Unexpected error",
                             f"The conversion stopped because of an internal error:\n\n{message}")
        self.statusBar().showMessage("Stopped by an internal error.")

    def _on_thread_finished(self) -> None:
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.deleteLater()
        self._set_running(False)

    # --------------------------------------------------------------- output actions
    def _open_output(self) -> None:
        if self.last_report and self.last_report.output_dir:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_report.output_dir)))

    def _export_report(self) -> None:
        if not self.last_report:
            return
        default = str((self.last_report.output_dir or Path.home()) / "conversion_report.csv")
        name, chosen = QFileDialog.getSaveFileName(self, "Export report", default,
                                                   "CSV spreadsheet (*.csv);;Text summary (*.txt)")
        if not name:
            return
        path = Path(name)
        as_txt = path.suffix.lower() == ".txt" or (not path.suffix and "txt" in chosen)
        if not path.suffix:
            path = path.with_suffix(".txt" if as_txt else ".csv")
        try:
            (write_text if as_txt else write_csv)(self.last_report, path)
        except OSError as exc:
            QMessageBox.critical(self, "Could not save report", f"{path}\n\n{exc.strerror or exc}")
            return
        self.statusBar().showMessage(f"Report saved: {path}")

    # ---------------------------------------------------------------------- state
    def _set_running(self, running: bool) -> None:
        self.source_panel.set_enabled_for_run(not running)
        self.settings_panel.set_enabled_for_run(not running)
        self.pause_button.setText("Pause")
        self._update_buttons()

    def _update_buttons(self) -> None:
        running = self.worker is not None
        self.start_button.setEnabled(not running and bool(self.items))
        self.pause_button.setEnabled(running)
        self.cancel_button.setEnabled(running)
        self.clear_button.setEnabled(not running and bool(self.sources))

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.worker is not None:
            answer = QMessageBox.question(
                self, "Conversion in progress",
                "A conversion is still running. Cancel it and exit?\n"
                "Files already converted are kept.")
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self.worker.cancel()
            self.worker.wait(15000)
        event.accept()
