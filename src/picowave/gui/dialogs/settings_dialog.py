"""Settings dialog: SDK mode and LLM backend, applied live.

SDK mode is safe to switch at any time (the compiler reads it per compile).
Switching the LLM rebuilds the client and reassigns it on the pipeline.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
)


class SettingsDialog(QDialog):
    def __init__(self, sdk_mode: str, llm_choice: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(320)
        form = QFormLayout(self)

        self.sdk = QComboBox()
        self.sdk.addItems(["mock", "real"])
        self.sdk.setCurrentText(sdk_mode)
        form.addRow("SDK", self.sdk)

        self.llm = QComboBox()
        self.llm.addItems(["auto", "ollama", "mock"])
        self.llm.setCurrentText(llm_choice)
        form.addRow("LLM backend", self.llm)

        note = QLabel("SDK affects the next compile. LLM applies to the next "
                      "command.")
        note.setWordWrap(True)
        form.addRow(note)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def values(self) -> tuple[str, str]:
        """Return (sdk_mode, llm_choice) selected by the user."""
        return self.sdk.currentText(), self.llm.currentText()
