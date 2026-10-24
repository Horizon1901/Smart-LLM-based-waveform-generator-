"""Pure helpers for the Result tab: ideal waveform synthesis and CSV reading.

No Qt here -- just numpy, so these are unit-testable on their own.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np


def looks_disconnected(mv: np.ndarray, full_scale_mv: float = 5000.0) -> bool:
    """Heuristic: does this look like a floating/unconnected input?

    An open channel typically reads near-zero for the overwhelming majority of
    samples with only small pickup/noise spikes, rather than a periodic signal
    with real amplitude. This is a hint, not a certainty -- a genuinely tiny or
    DC-near-zero real signal can also trigger it, so callers should phrase it
    as a suggestion ("check your connection?"), not a hard error.
    """
    if mv.size < 8:
        return False
    p2p = float(np.ptp(mv))
    near_zero_frac = float(np.mean(np.abs(mv) < max(5.0, 0.01 * full_scale_mv)))
    return near_zero_frac > 0.85 and p2p < 0.15 * full_scale_mv


def ideal_waveform(wave: str, freq_hz: float, amplitude_mvpp: float,
                   offset_mv: float, points: int = 2000,
                   min_cycles: float = 2.0, max_cycles: float = 20.0,
                   default_window_s: float = 0.005) -> Tuple[np.ndarray, np.ndarray]:
    """Return (time_ms, value_mv) for an ideal built-in waveform.

    This is a mathematical *representation* of the generated signal, not a
    measurement -- exactly what the siggen path calls for (it writes no data).

    The display window is a fixed duration (5 ms by default), NOT scaled to
    always show exactly N cycles of whatever frequency was passed in. That
    matters: if the window always showed exactly ``cycles`` periods, doubling
    the frequency would halve the window to match -- so the plot would always
    show "the same number of wiggles filling the same width" and a frequency
    change would be visually invisible even though the axis labels differed.
    With a fixed window, higher frequency visibly packs in more cycles and
    lower frequency visibly shows fewer -- which is what changing the
    frequency should look like. The window still adapts at the extremes
    (``min_cycles``/``max_cycles``) so a very low frequency doesn't render as
    a flat line and a very high frequency doesn't render as solid clutter.
    """
    freq = max(float(freq_hz), 1e-9)
    amp = float(amplitude_mvpp) / 2.0
    offset = float(offset_mv)
    period = 1.0 / freq

    window_s = default_window_s
    if window_s / period < min_cycles:
        window_s = min_cycles * period
    elif window_s / period > max_cycles:
        window_s = max_cycles * period

    t = np.linspace(0.0, window_s, points)
    phase = 2.0 * np.pi * freq * t

    w = (wave or "sine").lower()
    if w == "square":
        y = amp * np.sign(np.sin(phase))
    elif w == "triangle":
        y = amp * (2.0 / np.pi) * np.arcsin(np.sin(phase))
    elif w == "ramp_up":
        y = amp * (2.0 * ((freq * t) % 1.0) - 1.0)
    elif w == "ramp_down":
        y = amp * (1.0 - 2.0 * ((freq * t) % 1.0))
    elif w == "dc":
        y = np.zeros_like(t)
    else:  # sine (default)
        y = amp * np.sin(phase)

    return t * 1000.0, y + offset


@dataclass
class CsvCapture:
    """Parsed acquisition CSV."""
    time_ms: np.ndarray
    channels: Dict[str, np.ndarray] = field(default_factory=dict)  # "A"/"B" -> mV
    n_rows: int = 0
    header: List[str] = field(default_factory=list)
    rows: List[List[str]] = field(default_factory=list)  # raw, for the table view


def read_capture_csv(path: Path, max_table_rows: int = 5000) -> CsvCapture:
    """Read an ``acquisition_*.csv`` (sample,time_ns,chA_adc,chA_mv,chB_adc,chB_mv).

    Only channels with any non-zero millivolt data are treated as "present"
    (the generated C zero-fills a disabled channel).
    """
    path = Path(path)
    times_ns: List[float] = []
    a_mv: List[float] = []
    b_mv: List[float] = []
    header: List[str] = []
    raw_rows: List[List[str]] = []

    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for i, row in enumerate(reader):
            if i == 0:
                header = row
                continue
            if len(row) < 6:
                continue
            if len(raw_rows) < max_table_rows:
                raw_rows.append(row)
            try:
                times_ns.append(float(row[1]))
                a_mv.append(float(row[3]))
                b_mv.append(float(row[5]))
            except ValueError:
                continue

    t = np.asarray(times_ns, dtype=np.float64)
    a = np.asarray(a_mv, dtype=np.float64)
    b = np.asarray(b_mv, dtype=np.float64)
    time_ms = (t - t[0]) / 1e6 if t.size else t  # ns -> ms, zero-based

    channels: Dict[str, np.ndarray] = {}
    if a.size and np.any(a != 0):
        channels["A"] = a
    if b.size and np.any(b != 0):
        channels["B"] = b
    if not channels and a.size:  # flat capture: still show channel A
        channels["A"] = a

    return CsvCapture(time_ms=time_ms, channels=channels, n_rows=len(raw_rows),
                      header=header, rows=raw_rows)
