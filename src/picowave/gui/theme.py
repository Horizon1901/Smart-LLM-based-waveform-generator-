"""Dark engineering theme (Qt stylesheet) and shared plot colours."""
from __future__ import annotations

# Palette shared between the QSS and the matplotlib figures so plots match the UI.
BG = "#0f1216"
SURFACE = "#171b21"
SURFACE_2 = "#1d222a"
BORDER = "#2a313b"
TEXT = "#cdd6e0"
TEXT_MUTED = "#7a8696"
ACCENT = "#378add"
OK = "#1d9e75"
WARN = "#e0952f"
ERR = "#e24b4a"
TRACE_A = "#1d9e75"
TRACE_B = "#d4537e"

QSS = f"""
* {{ font-family: "Segoe UI", "DejaVu Sans", sans-serif; font-size: 13px; }}
QMainWindow, QWidget {{ background: {BG}; color: {TEXT}; }}
QLabel#sectionTitle {{ color: {TEXT_MUTED}; font-size: 12px; }}
QLabel#statusBadgeOk {{ color: {OK}; }}
QLabel#statusBadgeWarn {{ color: {WARN}; }}
QFrame#panel, QTabWidget::pane {{ background: {SURFACE}; border: 1px solid {BORDER}; }}
QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QTableWidget {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 4px;
    selection-background-color: {ACCENT};
}}
QPushButton {{
    background: {SURFACE_2}; color: {TEXT};
    border: 1px solid {BORDER}; border-radius: 6px; padding: 6px 12px;
}}
QPushButton:hover {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: {TEXT_MUTED}; }}
QPushButton#primary {{ background: {ACCENT}; color: white; border: none; }}
QTabBar::tab {{
    background: {SURFACE}; color: {TEXT_MUTED};
    border: 1px solid {BORDER}; border-bottom: none;
    padding: 6px 14px; margin-right: 2px;
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{ background: {SURFACE_2}; color: {TEXT}; }}
QHeaderView::section {{
    background: {SURFACE}; color: {TEXT_MUTED};
    border: 1px solid {BORDER}; padding: 4px;
}}
QStatusBar {{ background: {SURFACE}; color: {TEXT_MUTED}; }}
QScrollBar:vertical {{ background: {SURFACE}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; }}
"""


def apply_theme(app) -> None:
    app.setStyleSheet(QSS)
