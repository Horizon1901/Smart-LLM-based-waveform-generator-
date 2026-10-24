"""Poll backend availability off the GUI thread (Ollama can block up to 5 s)."""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal


class StatusWorker(QThread):
    """Emit (llm_is_mock, ollama_ok) after checking availability."""

    status = Signal(bool, bool)

    def __init__(self, llm, parent=None) -> None:
        super().__init__(parent)
        self._llm = llm

    def run(self) -> None:
        is_mock = type(self._llm).__name__ == "MockLLM"
        ok = False
        if not is_mock:
            try:
                ok = bool(self._llm.available())
            except Exception:  # noqa: BLE001
                ok = False
        self.status.emit(is_mock, ok)
