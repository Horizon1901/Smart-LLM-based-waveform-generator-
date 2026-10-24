"""Generated C tab: displays the C source the pipeline just produced.

Syntax highlighting is added in a later step; this shows the real source now,
in a monospace view, with copy and save.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QVBoxLayout,
    QWidget,
)

from ..theme import TEXT_MUTED
from ..syntax import CSyntaxHighlighter


class CodeTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._path: Optional[Path] = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        head = QHBoxLayout()
        self.caption = QLabel("Generated C will appear here after a command.")
        self.caption.setStyleSheet(f"color:{TEXT_MUTED};")
        head.addWidget(self.caption)
        head.addStretch(1)
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self._copy)
        self.save_btn = QPushButton("Save as...")
        self.save_btn.clicked.connect(self._save)
        head.addWidget(self.copy_btn)
        head.addWidget(self.save_btn)
        layout.addLayout(head)

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setFont(QFont("DejaVu Sans Mono", 10))
        self.view.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._highlighter = CSyntaxHighlighter(self.view.document())
        layout.addWidget(self.view, 1)

    def show_file(self, path: Path) -> None:
        path = Path(path)
        self._path = path
        try:
            self.view.setPlainText(path.read_text(encoding="utf-8"))
            self.caption.setText(f"Generated C — {path.name}")
        except Exception as exc:  # noqa: BLE001
            self.view.setPlainText(f"// could not read {path}: {exc}")

    def _copy(self) -> None:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.view.toPlainText())

    def _save(self) -> None:
        default = self._path.name if self._path else "generated.c"
        target, _ = QFileDialog.getSaveFileName(self, "Save generated C", default,
                                                "C source (*.c)")
        if target:
            Path(target).write_text(self.view.toPlainText(), encoding="utf-8")
