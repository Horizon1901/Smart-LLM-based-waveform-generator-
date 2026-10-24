"""Left column: command input, Run/voice buttons, assistant thread, history."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
    QTextEdit, QVBoxLayout,
)

from ..theme import ACCENT, TEXT_MUTED


class CommandPanel(QFrame):
    """Emits ``command_submitted(text)`` when the user runs a command."""

    command_submitted = Signal(str)
    voice_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        self.setFixedWidth(268)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        root.addWidget(self._title("Command"))
        self.input = QLineEdit()
        self.input.setPlaceholderText("Generate a square wave at 3000 Hz")
        self.input.returnPressed.connect(self._submit)
        root.addWidget(self.input)

        row = QHBoxLayout()
        self.run_btn = QPushButton("Run")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._submit)
        row.addWidget(self.run_btn)
        self.mic_btn = QPushButton("Voice")
        self.mic_btn.setToolTip("Listen for a spoken command")
        self.mic_btn.clicked.connect(self.voice_requested)
        row.addWidget(self.mic_btn)
        root.addLayout(row)

        self.speak_check = QCheckBox("Speak results")
        root.addWidget(self.speak_check)

        root.addWidget(self._title("Assistant"))
        self.thread = QTextEdit()
        self.thread.setReadOnly(True)
        root.addWidget(self.thread, 1)

        root.addWidget(self._title("History"))
        self.history = QListWidget()
        self.history.setMaximumHeight(120)
        root.addWidget(self.history)

    @staticmethod
    def _title(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setObjectName("sectionTitle")
        return lbl

    # -- interaction -------------------------------------------------------
    def _submit(self) -> None:
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.command_submitted.emit(text)

    def set_busy(self, busy: bool) -> None:
        self.run_btn.setEnabled(not busy)
        self.mic_btn.setEnabled(not busy)
        self.input.setEnabled(not busy)
        self.run_btn.setText("Running..." if busy else "Run")

    def set_listening(self, listening: bool) -> None:
        self.mic_btn.setText("Listening..." if listening else "Voice")
        self.mic_btn.setEnabled(not listening)
        self.run_btn.setEnabled(not listening)

    def speak_enabled(self) -> bool:
        return self.speak_check.isChecked()

    # -- content -----------------------------------------------------------
    def add_user(self, text: str) -> None:
        self.thread.append(f'<div style="color:{ACCENT};margin-top:6px;">'
                           f'&gt; {_esc(text)}</div>')
        self.history.insertItem(0, text)

    def add_assistant(self, text: str) -> None:
        self.thread.append(f'<div style="color:{TEXT_MUTED};">{_esc(text)}</div>')


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
