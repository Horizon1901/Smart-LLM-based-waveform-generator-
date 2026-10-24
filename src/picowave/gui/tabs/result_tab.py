"""Result tab: auto-displays a visual for the last successful operation.

  * signal generation -> ideal mathematical waveform (a representation)
  * acquisition        -> the real captured samples from the newest CSV
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ..theme import TEXT_MUTED, TRACE_A, TRACE_B, WARN
from ..waveform_math import ideal_waveform, looks_disconnected, read_capture_csv
from .mpl_canvas import MplCanvas


class ResultTab(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        head = QHBoxLayout()
        self.caption = QLabel("Run a command to see its result here.")
        self.caption.setStyleSheet(f"color:{TEXT_MUTED};")
        head.addWidget(self.caption)
        head.addStretch(1)
        self.save_btn = QPushButton("Save image")
        self.save_btn.clicked.connect(self._save_image)
        head.addWidget(self.save_btn)
        layout.addLayout(head)
        self.canvas = MplCanvas(self)
        layout.addWidget(self.canvas, 1)
        self.canvas.message("No result yet")

    def _save_image(self) -> None:
        target, _ = QFileDialog.getSaveFileName(
            self, "Save plot image", "waveform.png",
            "PNG image (*.png);;PDF (*.pdf)")
        if target:
            self.canvas.fig.savefig(target, facecolor=self.canvas.fig.get_facecolor(),
                                    dpi=150)

    # -- signal generation: ideal waveform --------------------------------
    def show_siggen(self, wave: str, freq_hz: float, amplitude_mvpp: float,
                    offset_mv: float) -> None:
        t_ms, y_mv = ideal_waveform(wave, freq_hz, amplitude_mvpp, offset_mv)
        self.caption.setText(
            f"Ideal waveform — {wave} · {freq_hz:g} Hz · "
            f"{amplitude_mvpp/1000:g} Vpp · offset {offset_mv:g} mV")
        self.caption.setStyleSheet(f"color:{TEXT_MUTED};")
        self.canvas.reset()
        self.canvas.ax.plot(t_ms, y_mv, color=TRACE_A, linewidth=1.8)
        self.canvas.ax.set_xlabel("time (ms)")
        self.canvas.ax.set_ylabel("amplitude (mV)")
        self.canvas.ax.margins(x=0)
        self.canvas.draw_idle()

    # -- acquisition: real CSV --------------------------------------------
    def show_csv(self, path: Path) -> None:
        try:
            cap = read_capture_csv(path)
        except Exception as exc:  # noqa: BLE001
            self.canvas.message(f"Could not read CSV:\n{exc}")
            return
        if not cap.channels:
            self.canvas.message("Capture contained no channel data")
            return
        caption = f"Acquired capture — {Path(path).name} ({cap.time_ms.size} samples)"
        flat_channels = [name for name, mv in cap.channels.items()
                         if looks_disconnected(mv)]
        self.caption.setText(caption)
        self.caption.setStyleSheet(f"color:{TEXT_MUTED};")
        if flat_channels:
            which = " and ".join(flat_channels)
            self.caption.setText(
                f"{caption} — Channel {which} looks flat/near-zero. If you "
                "expected a real signal, check that it's physically "
                "connected to the input.")
            self.caption.setStyleSheet(f"color:{WARN};")
        self.canvas.reset()
        colors = {"A": TRACE_A, "B": TRACE_B}
        for name, mv in cap.channels.items():
            self.canvas.ax.plot(cap.time_ms, mv, linewidth=1.2,
                                color=colors.get(name, TRACE_A),
                                label=f"Channel {name}")
        self.canvas.ax.set_xlabel("time (ms)")
        self.canvas.ax.set_ylabel("voltage (mV)")
        self.canvas.ax.margins(x=0)
        leg = self.canvas.ax.legend(loc="upper right", fontsize=8,
                                    facecolor="none", edgecolor="none",
                                    labelcolor=TEXT_MUTED)
        if leg:
            leg.get_frame().set_alpha(0)
        self.canvas.draw_idle()

    def show_message(self, text: str) -> None:
        self.caption.setText(text)
        self.canvas.message(text)
