"""Run one pipeline command on a background thread.

``Pipeline.process_command`` calls the LLM and shells out to gcc + the compiled
binary, which can take seconds. Running it on a ``QThread`` keeps the GUI
responsive. Results come back via signals delivered to the GUI thread.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from ...pipeline import CommandOutcome, Pipeline


class CommandWorker(QThread):
    started_cmd = Signal(str)          # the command text, when work begins
    finished_cmd = Signal(object)      # CommandOutcome on success
    failed = Signal(str)               # error string if the pipeline raised

    def __init__(self, pipeline: Pipeline, text: str, parent=None) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._text = text

    def run(self) -> None:  # executes on the worker thread
        self.started_cmd.emit(self._text)
        try:
            outcome: CommandOutcome = self._pipeline.process_command(self._text)
        except Exception as exc:  # noqa: BLE001 - surface, don't crash the GUI
            self.failed.emit(f"{type(exc).__name__}: {exc}")
            return
        self.finished_cmd.emit(outcome)
