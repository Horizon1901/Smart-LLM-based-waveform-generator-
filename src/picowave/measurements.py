"""Compute measurements from a captured CSV, and find the most recent one.

Pure, backend-level (no GUI/Qt dependency) so "process" works identically from
the CLI and the desktop app -- the app doesn't need any special-case code, it
just gets the same spoken summary and the same csv_path back on the outcome.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


def find_csv_by_id(generated_dir: Path, capture_id: int) -> Optional[Path]:
    """Look up a capture by its literal, stable ID (acquisition_NNN.csv),
    as opposed to find_recent_csvs' ordinal "Nth most recent" position.

    Unlike an ordinal reference, this ALWAYS points at the same file
    regardless of what else has been captured since -- useful once you
    already know the specific ID (e.g. from a previous "process" response,
    which now always states the real filename it used).
    """
    path = Path(generated_dir) / f"acquisition_{capture_id:03d}.csv"
    return path if path.exists() else None


def find_latest_csv(generated_dir: Path) -> Optional[Path]:
    """Return the most recently generated acquisition_*.csv, or None.

    Stateless by design -- "process" always operates on whatever capture is
    actually newest on disk, so it works correctly even across an app
    restart, without needing to track "the last capture" as session state.
    """
    recent = find_recent_csvs(generated_dir, 1)
    return recent[0] if recent else None


def find_recent_csvs(generated_dir: Path, n: int) -> List[Path]:
    """Return up to the ``n`` most recent acquisition_*.csv files, newest
    first -- so "file 1" (1-indexed, matching how people naturally refer to
    "the first/most recent one") is index 0, "file 2" is index 1, etc.
    """
    candidates: List[tuple] = []
    for p in Path(generated_dir).glob("acquisition_*.csv"):
        m = re.search(r"acquisition_(\d+)\.csv$", p.name)
        if m:
            candidates.append((int(m.group(1)), p))
    candidates.sort(key=lambda pair: pair[0], reverse=True)  # newest first
    return [p for _, p in candidates[:n]]


@dataclass
class ChannelMeasurements:
    channel: str
    n_samples: int
    vpp_mv: float
    mean_mv: float
    min_mv: float
    max_mv: float
    rms_mv: float
    freq_hz: Optional[float]        # None if no reliable periodicity was found
    shape: Optional[str] = None     # "sine" | "square" | "triangle" | None
    shape_confidence: float = 0.0   # 0..1 correlation against the best match


# Waveform shapes classify_waveform can recognise. Deliberately a small,
# closed set of well-separated ideal shapes -- not an open-ended guess -- so
# "none of the above" is a real, meaningful answer rather than a catch-all.
_SHAPE_FUNCS = {
    "sine": lambda phase: np.sin(phase),
    "square": lambda phase: np.sign(np.sin(phase)),
    "triangle": lambda phase: (2.0 / np.pi) * np.arcsin(np.sin(phase)),
}

_CLASSIFY_MIN_CONFIDENCE = 0.85  # below this, report "none of the above"
_PHASE_STEPS = 36  # 10-degree resolution when searching for the best phase align
# The frequency estimate feeding this has some real error (zero-crossing
# counting depends on how sample times land relative to the true crossings),
# and over many cycles even a few percent of frequency error compounds into
# large phase drift by the end of the window -- enough to wreck correlation
# for a genuinely correctly-shaped signal. Search a small neighborhood around
# the estimate, not just the estimate itself, so classification is robust to
# realistic estimation error instead of requiring a suspiciously exact one.
_FREQ_SEARCH_PCT = 6.0
_FREQ_STEPS = 9


def classify_waveform(t_ns: np.ndarray, mv: np.ndarray,
                      freq_hz: Optional[float]) -> tuple:
    """Classify a captured signal's shape as sine/square/triangle/None.

    This is deterministic signal analysis, not an LLM guess: the real signal
    is detrended and amplitude-normalised, then correlated against ideal
    reference waveforms of each known shape -- swept across both phase offset
    and a small neighborhood around the estimated frequency (both are
    genuinely uncertain: the real signal's phase is unknown, and the
    frequency estimate has some real error that compounds over many cycles).
    The shape/frequency/phase combination with the highest peak correlation
    wins, but only if that correlation clears ``_CLASSIFY_MIN_CONFIDENCE`` --
    otherwise this correctly reports "none of the above" rather than forcing
    a low-confidence guess onto an irregular or unrecognised signal.

    Returns (shape_name_or_None, confidence 0..1).
    """
    if freq_hz is None or freq_hz <= 0 or mv.size < 16:
        return None, 0.0

    detrended = mv - np.mean(mv)
    peak = np.max(np.abs(detrended))
    if peak <= 0:
        return None, 0.0
    normalized = detrended / peak
    normalized_c = normalized - np.mean(normalized)
    norm_energy = np.sum(normalized_c ** 2)
    if norm_energy <= 0:
        return None, 0.0

    t_s = (t_ns - t_ns[0]) * 1e-9
    freq_candidates = np.linspace(
        freq_hz * (1 - _FREQ_SEARCH_PCT / 100),
        freq_hz * (1 + _FREQ_SEARCH_PCT / 100),
        _FREQ_STEPS,
    )

    best_shape: Optional[str] = None
    best_score = 0.0
    for shape_name, shape_fn in _SHAPE_FUNCS.items():
        best_for_shape = 0.0
        for f in freq_candidates:
            base_phase = 2.0 * np.pi * f * t_s
            for step in range(_PHASE_STEPS):
                offset = 2.0 * np.pi * step / _PHASE_STEPS
                reference = shape_fn(base_phase + offset)
                ref_c = reference - np.mean(reference)
                ref_energy = np.sum(ref_c ** 2)
                if ref_energy <= 0:
                    continue
                corr = float(np.sum(ref_c * normalized_c) /
                            np.sqrt(ref_energy * norm_energy))
                if corr > best_for_shape:
                    best_for_shape = corr
        if best_for_shape > best_score:
            best_score = best_for_shape
            best_shape = shape_name

    if best_score < _CLASSIFY_MIN_CONFIDENCE:
        return None, best_score
    return best_shape, best_score


def _read_channels(path: Path) -> Dict[str, tuple]:
    """Read the CSV, returning {"A"/"B": (t_ns array, mv array)} for channels
    that have any non-zero data (a disabled/unconnected channel is written as
    all-zero and is skipped, same convention used elsewhere in this project).
    """
    t_ns: List[float] = []
    a_mv: List[float] = []
    b_mv: List[float] = []
    with open(path, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        for i, row in enumerate(reader):
            if i == 0 or len(row) < 6:
                continue
            try:
                t_ns.append(float(row[1]))
                a_mv.append(float(row[3]))
                b_mv.append(float(row[5]))
            except ValueError:
                continue
    t = np.asarray(t_ns, dtype=np.float64)
    a = np.asarray(a_mv, dtype=np.float64)
    b = np.asarray(b_mv, dtype=np.float64)
    out: Dict[str, tuple] = {}
    if a.size and np.any(a != 0):
        out["A"] = (t, a)
    if b.size and np.any(b != 0):
        out["B"] = (t, b)
    if not out and a.size:  # genuinely flat capture: still report channel A
        out["A"] = (t, a)
    return out


def _estimate_frequency_hz(t_ns: np.ndarray, mv: np.ndarray) -> Optional[float]:
    """Zero-crossing based frequency estimate. Simple and robust for the
    periodic waveforms this project generates; returns None rather than a
    misleading number when the signal doesn't look periodic enough to trust.
    """
    if mv.size < 8:
        return None
    detrended = mv - np.mean(mv)
    signs = np.sign(detrended)
    signs[signs == 0] = 1
    crossings = int(np.sum(np.diff(signs) != 0))
    if crossings < 2:
        return None
    total_time_s = (t_ns[-1] - t_ns[0]) * 1e-9
    if total_time_s <= 0:
        return None
    return (crossings / 2.0) / total_time_s


def measure_csv(path: Path) -> List[ChannelMeasurements]:
    """Compute measurements for every channel with real data in the CSV."""
    channels = _read_channels(Path(path))
    results: List[ChannelMeasurements] = []
    for name, (t_ns, mv) in channels.items():
        freq = _estimate_frequency_hz(t_ns, mv)
        shape, confidence = classify_waveform(t_ns, mv, freq)
        results.append(ChannelMeasurements(
            channel=name,
            n_samples=int(mv.size),
            vpp_mv=float(np.ptp(mv)) if mv.size else 0.0,
            mean_mv=float(np.mean(mv)) if mv.size else 0.0,
            min_mv=float(np.min(mv)) if mv.size else 0.0,
            max_mv=float(np.max(mv)) if mv.size else 0.0,
            rms_mv=float(np.sqrt(np.mean(np.square(mv)))) if mv.size else 0.0,
            freq_hz=freq,
            shape=shape,
            shape_confidence=confidence,
        ))
    return results


def summarize(measurements: List[ChannelMeasurements]) -> str:
    """A short, spoken-friendly summary of the measurements."""
    if not measurements:
        return "No channel data to summarize."
    parts = []
    for m in measurements:
        freq_part = (f"estimated frequency {m.freq_hz:.0f} Hz, "
                    if m.freq_hz else "frequency not clearly periodic, ")
        if m.shape:
            shape_part = f"looks like a {m.shape} wave ({m.shape_confidence*100:.0f}% match), "
        else:
            shape_part = "does not clearly match sine, square, or triangle, "
        parts.append(
            f"Channel {m.channel}: {shape_part}{freq_part}"
            f"{m.vpp_mv:.0f} millivolts peak to peak, "
            f"mean {m.mean_mv:.0f} millivolts, "
            f"range {m.min_mv:.0f} to {m.max_mv:.0f} millivolts, "
            f"{m.rms_mv:.0f} millivolts RMS."
        )
    return " ".join(parts)
