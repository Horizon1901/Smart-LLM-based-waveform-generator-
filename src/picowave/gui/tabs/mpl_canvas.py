"""A dark-themed Matplotlib canvas embedded in Qt, shared by the plot tabs."""
from __future__ import annotations

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from ..theme import BG, BORDER, SURFACE_2, TEXT, TEXT_MUTED


class MplCanvas(FigureCanvasQTAgg):
    """FigureCanvas with a single styled axes and a couple of helpers."""

    def __init__(self, parent=None) -> None:
        self.fig = Figure(figsize=(5, 3), tight_layout=True)
        self.fig.patch.set_facecolor(BG)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)
        self._style_axes()

    def _style_axes(self) -> None:
        ax = self.ax
        ax.set_facecolor(SURFACE_2)
        for spine in ax.spines.values():
            spine.set_color(BORDER)
        ax.tick_params(colors=TEXT_MUTED, labelsize=9)
        ax.grid(True, color=BORDER, linewidth=0.5, alpha=0.8)
        ax.xaxis.label.set_color(TEXT)
        ax.yaxis.label.set_color(TEXT)
        ax.title.set_color(TEXT)

    def reset(self) -> None:
        self.ax.clear()
        self._style_axes()

    def message(self, text: str) -> None:
        self.reset()
        self.ax.text(0.5, 0.5, text, ha="center", va="center",
                     color=TEXT_MUTED, fontsize=11, transform=self.ax.transAxes)
        self.ax.set_xticks([])
        self.ax.set_yticks([])
        self.draw_idle()
