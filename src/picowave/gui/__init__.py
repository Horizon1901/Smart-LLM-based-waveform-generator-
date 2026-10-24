"""Desktop GUI for PicoWave Assistant (PySide6 + Matplotlib).

A thin, read-only presentation layer over the existing pipeline. The GUI never
touches the PicoScope directly: it runs the same ``Pipeline.process_command``
the CLI uses (on a worker thread) and visualises the *outputs* -- an ideal
mathematical waveform for signal generation, and the real CSV for acquisition.

Launch:  python -m picowave.gui  [--sdk mock|real] [--llm auto|ollama|mock]
The CLI (``python -m picowave.main``) is unchanged and still works.
"""
from __future__ import annotations

import os

# matplotlib must bind to PySide6 (not PyQt) -- set before any mpl import.
os.environ.setdefault("QT_API", "pyside6")

from .app import run  # noqa: E402

__all__ = ["run"]
