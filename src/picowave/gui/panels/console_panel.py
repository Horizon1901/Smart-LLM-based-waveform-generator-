"""Bottom console: colour-coded backend activity from the log bridge."""
from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from ..theme import ERR, OK, TEXT, TEXT_MUTED, WARN

_LEVEL_COLOR = {
    "debug": TEXT_MUTED, "stage": TEXT, "info": TEXT,
    "warning": WARN, "error": ERR,
}


class ConsolePanel(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("panel")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 6, 8, 8)
        root.setSpacing(4)

        head = QHBoxLayout()
        title = QLabel("Console")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        clear = QPushButton("Clear")
        clear.clicked.connect(self._clear)
        head.addWidget(clear)
        root.addLayout(head)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(2000)
        self.view.setFont(QFont("DejaVu Sans Mono", 10))
        self.view.setFixedHeight(150)
        root.addWidget(self.view)

    # -- slot for LogBridge.message ---------------------------------------
    def append(self, level: str, text: str) -> None:
        color = _LEVEL_COLOR.get(level, TEXT)
        safe = (text.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))
        self.view.appendHtml(f'<span style="color:{color};">{safe}</span>')

    def _clear(self) -> None:
        self.view.clear()
