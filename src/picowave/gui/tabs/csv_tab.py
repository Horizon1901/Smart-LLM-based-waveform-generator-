"""CSV viewer tab: shows the newest acquisition CSV as a table and a plot."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QAbstractItemView, QLabel, QSplitter, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt

from ..theme import TEXT_MUTED, TRACE_A, TRACE_B, WARN
from ..waveform_math import looks_disconnected, read_capture_csv
from .mpl_canvas import MplCanvas


class CsvTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.caption = QLabel("A capture CSV will appear here after acquisition.")
        self.caption.setStyleSheet(f"color:{TEXT_MUTED};")
        layout.addWidget(self.caption)

        split = QSplitter(Qt.Vertical)
        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        split.addWidget(self.table)
        self.canvas = MplCanvas(self)
        split.addWidget(self.canvas)
        split.setSizes([200, 200])
        layout.addWidget(split, 1)
        self.canvas.message("No capture yet")

    def show_csv(self, path: Path, max_table_rows: int = 500) -> None:
        path = Path(path)
        try:
            cap = read_capture_csv(path)
        except Exception as exc:  # noqa: BLE001
            self.caption.setText(f"Could not read {path.name}: {exc}")
            return
        self.caption.setText(f"{path.name} — {cap.time_ms.size} samples")
        self.caption.setStyleSheet(f"color:{TEXT_MUTED};")
        flat_channels = [name for name, mv in cap.channels.items()
                         if looks_disconnected(mv)]
        if flat_channels:
            which = " and ".join(flat_channels)
            self.caption.setText(
                f"{path.name} — {cap.time_ms.size} samples — Channel {which} "
                "looks flat/near-zero (check the connection if this is unexpected)")
            self.caption.setStyleSheet(f"color:{WARN};")

        # Table (capped for responsiveness).
        rows = cap.rows[:max_table_rows]
        self.table.setColumnCount(len(cap.header))
        self.table.setHorizontalHeaderLabels(cap.header)
        self.table.setRowCount(len(rows))
        for r, row in enumerate(rows):
            for c, val in enumerate(row):
                self.table.setItem(r, c, QTableWidgetItem(val))
        self.table.resizeColumnsToContents()

        # Plot.
        self.canvas.reset()
        if cap.channels:
            colors = {"A": TRACE_A, "B": TRACE_B}
            for name, mv in cap.channels.items():
                self.canvas.ax.plot(cap.time_ms, mv, linewidth=1.0,
                                    color=colors.get(name, TRACE_A),
                                    label=f"Channel {name}")
            self.canvas.ax.set_xlabel("time (ms)")
            self.canvas.ax.set_ylabel("voltage (mV)")
            self.canvas.ax.margins(x=0)
            self.canvas.ax.legend(loc="upper right", fontsize=8,
                                  facecolor="none", edgecolor="none",
                                  labelcolor=TEXT_MUTED)
        self.canvas.draw_idle()
