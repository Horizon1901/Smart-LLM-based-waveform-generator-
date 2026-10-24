"""Launch a real gnuplot window for one or more captured CSVs.

Runs gnuplot as a genuinely separate, detached process (``-p`` keeps its
window open after the script finishes) so it never blocks the caller -- the
CLI and the GUI both just fire-and-forget this. If gnuplot isn't installed,
this degrades to returning a clear message instead of raising, matching the
rest of this project's "never crash, always explain" convention.

Supports the same things you'd type directly into gnuplot -- explicit column
numbers (``using 1:3``) and a plot style (``lines``/``points``/
``linespoints``) -- so a spoken command like "use column 1 and 3 with lp" maps
directly onto real gnuplot syntax rather than a fixed, hardcoded plot shape.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# CSV column indices (1-based, as gnuplot expects): sample,time_ns,chA_adc,chA_mv,chB_adc,chB_mv
_TIME_COL = 2
_CHANNEL_COL = {"A": 4, "B": 6}
_SERIES_COLORS = ["#1d9e75", "#d4537e", "#378add", "#e0952f", "#a56cd6"]

_STYLE_ALIASES = {
    "lines": "lines", "line": "lines", "l": "lines",
    "points": "points", "point": "points", "p": "points",
    "linespoints": "linespoints", "lp": "linespoints",
    "impulses": "impulses", "steps": "steps",
}
DEFAULT_STYLE = "lines"


def gnuplot_available() -> bool:
    return shutil.which("gnuplot") is not None


def normalize_style(style: Optional[str]) -> str:
    """Map a spoken/typed style word (e.g. "lp", "points") to real gnuplot
    "with" syntax. Falls back to the default for anything unrecognised,
    rather than passing through a word gnuplot itself would reject.
    """
    if not style:
        return DEFAULT_STYLE
    return _STYLE_ALIASES.get(style.strip().lower(), DEFAULT_STYLE)


@dataclass
class PlotSpec:
    """One CSV's contribution to a (possibly multi-file) gnuplot window."""
    csv_path: Path
    channels: List[str] = field(default_factory=lambda: ["A", "B"])
    title: Optional[str] = None  # None -> derive from filename/channel


def _build_script(specs: List[PlotSpec], x_col: Optional[int] = None,
                  y_col: Optional[int] = None,
                  style: str = DEFAULT_STYLE) -> str:
    """Build a gnuplot script for one or more files.

    If ``x_col``/``y_col`` are given (a direct, verbal column override -- "use
    column 1 and 3"), every series plots exactly that column pair, matching
    what typing ``using 1:3`` by hand would do. Otherwise each file plots its
    real channel data (time vs mV) per enabled channel, same as before.
    """
    gnu_style = normalize_style(style)
    plots = []
    color_i = 0
    for spec in specs:
        path_str = spec.csv_path.as_posix()
        if x_col is not None and y_col is not None:
            label = spec.title or spec.csv_path.stem
            color = _SERIES_COLORS[color_i % len(_SERIES_COLORS)]
            color_i += 1
            plots.append(
                f"'{path_str}' using {x_col}:{y_col} every ::1 "
                f"with {gnu_style} lw 2 lc rgb '{color}' title '{label}'"
            )
            continue
        channels = [c for c in spec.channels if c in _CHANNEL_COL] or ["A"]
        for ch in channels:
            col = _CHANNEL_COL[ch]
            base_label = spec.title or spec.csv_path.stem
            label = f"{base_label} ch {ch}" if len(channels) > 1 or not spec.title \
                else base_label
            color = _SERIES_COLORS[color_i % len(_SERIES_COLORS)]
            color_i += 1
            plots.append(
                f"'{path_str}' using {_TIME_COL}:{col} every ::1 "
                f"with {gnu_style} lw 2 lc rgb '{color}' title '{label}'"
            )

    plot_line = "plot " + ", ".join(plots)
    y_label = "voltage (mV)" if y_col is None else f"column {y_col}"
    x_label = "time (ns)" if x_col is None else f"column {x_col}"
    title = "LLM Project capture" if len(specs) == 1 else \
        "LLM Project -- comparison"
    return (
        "set datafile separator ','\n"
        "set grid\n"
        f"set xlabel '{x_label}'\n"
        f"set ylabel '{y_label}'\n"
        f"set title '{title}'\n"
        f"{plot_line}\n"
        "pause mouse close\n"
    )


def _spawn(script: str) -> Optional[str]:
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".gp", prefix="picowave_", delete=False)
    tmp.write(script)
    tmp.close()
    try:
        # Detached: gnuplot -p keeps the window open after the script runs,
        # and Popen (not run/check_call) means this never blocks the caller
        # waiting for the user to close the plot window.
        subprocess.Popen(
            ["gnuplot", "-p", tmp.name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:  # noqa: BLE001 - never let plotting break a command
        return f"Could not launch gnuplot: {exc}"
    return None


def launch_gnuplot(csv_path: Path, channels: Optional[List[str]] = None,
                   title: str = "LLM Project capture") -> Optional[str]:
    """Spawn gnuplot in its own window for a single CSV (the common case).

    Returns None on a (best-effort) success, or a short human-readable
    message explaining why it couldn't be launched -- never raises.
    """
    return launch_gnuplot_multi(
        [PlotSpec(csv_path=Path(csv_path), channels=channels or ["A", "B"],
                  title=None)])


def launch_gnuplot_multi(specs: List[PlotSpec], x_col: Optional[int] = None,
                         y_col: Optional[int] = None,
                         style: str = DEFAULT_STYLE) -> Optional[str]:
    """Spawn gnuplot in its own window plotting one or more CSVs together --
    the multi-file "process file 1 and file 2, titled X and Y" case.
    """
    if not specs:
        return "No captures to plot."
    missing = [s.csv_path.name for s in specs if not Path(s.csv_path).exists()]
    if missing:
        return f"Capture file(s) not found: {', '.join(missing)}"
    if not gnuplot_available():
        return "gnuplot is not installed -- showing the built-in plot only."

    script = _build_script(specs, x_col=x_col, y_col=y_col, style=style)
    return _spawn(script)
