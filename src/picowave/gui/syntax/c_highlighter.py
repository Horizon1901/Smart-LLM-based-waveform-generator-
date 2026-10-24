"""A QSyntaxHighlighter for C, tuned for the dark theme.

Highlights preprocessor lines, keywords, common (and fixed-width) types, strings,
character literals, numbers, functions, and both line and block comments.
"""
from __future__ import annotations

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import (
    QColor, QSyntaxHighlighter, QTextCharFormat, QTextDocument, QFont,
)

_KEYWORDS = (
    "auto break case const continue default do else enum extern for goto if "
    "inline register restrict return sizeof static struct switch typedef union "
    "volatile while _Bool"
).split()

_TYPES = (
    "void char short int long float double signed unsigned "
    "int8_t int16_t int32_t int64_t uint8_t uint16_t uint32_t uint64_t "
    "size_t FILE"
).split()


def _fmt(color: str, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Bold)
    if italic:
        f.setFontItalic(True)
    return f


class CSyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []

        kw = _fmt("#569cd6")
        for w in _KEYWORDS:
            self._rules.append((QRegularExpression(rf"\b{w}\b"), kw))
        ty = _fmt("#4ec9b0")
        for w in _TYPES:
            self._rules.append((QRegularExpression(rf"\b{w}\b"), ty))

        # function-like: identifier followed by '('
        self._rules.append(
            (QRegularExpression(r"\b[A-Za-z_][A-Za-z0-9_]*(?=\s*\()"),
             _fmt("#dcdcaa")))
        # numbers (int, float, hex)
        self._rules.append(
            (QRegularExpression(r"\b(0[xX][0-9a-fA-F]+|\d+\.?\d*[fFuUlL]*)\b"),
             _fmt("#b5cea8")))
        # strings and char literals
        self._rules.append((QRegularExpression(r'"[^"\\]*(\\.[^"\\]*)*"'),
                            _fmt("#ce9178")))
        self._rules.append((QRegularExpression(r"'([^'\\]|\\.)'"),
                            _fmt("#ce9178")))
        # preprocessor
        self._rules.append((QRegularExpression(r"^\s*#.*$"), _fmt("#c586c0")))
        # line comments (added last so it wins on a line)
        self._rules.append((QRegularExpression(r"//[^\n]*"),
                            _fmt("#6a9955", italic=True)))

        self._comment_start = QRegularExpression(r"/\*")
        self._comment_end = QRegularExpression(r"\*/")
        self._comment_fmt = _fmt("#6a9955", italic=True)

    def highlightBlock(self, text: str) -> None:
        for pattern, fmt in self._rules:
            it = pattern.globalMatch(text)
            while it.hasNext():
                m = it.next()
                self.setFormat(m.capturedStart(), m.capturedLength(), fmt)

        # Multi-line /* ... */ comments via block state.
        self.setCurrentBlockState(0)
        start = 0
        if self.previousBlockState() != 1:
            m = self._comment_start.match(text)
            start = m.capturedStart() if m.hasMatch() else -1
        while start >= 0:
            end_match = self._comment_end.match(text, start)
            if end_match.hasMatch():
                length = end_match.capturedEnd() - start
            else:
                self.setCurrentBlockState(1)
                length = len(text) - start
            self.setFormat(start, length, self._comment_fmt)
            nxt = self._comment_start.match(text, start + length)
            start = nxt.capturedStart() if nxt.hasMatch() else -1
