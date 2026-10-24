"""Logging for PicoWave Assistant.

Two sinks:
  * a rotating human-readable app log (logs/picowave.log), and
  * a structured JSONL session log (logs/session-<ts>.jsonl) that records every
    stage the prompt asks for: speech recognition, recognised text, LLM prompt,
    generated C, compiler output, execution output, runtime errors, timestamps.
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

# A listener receives (stage, fields_dict) for every structured event. Used by
# the GUI console to mirror pipeline activity live. None are registered in CLI
# use, so behaviour there is unchanged.
EventListener = Callable[[str, dict], None]


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


class SessionLogger:
    """Wraps a stdlib logger plus a JSONL event stream for one run."""

    def __init__(self, log_dir: Path, verbose: bool = True):
        log_dir.mkdir(parents=True, exist_ok=True)
        self.session_id = _timestamp()
        self.jsonl_path = log_dir / f"session-{self.session_id}.jsonl"
        self._listeners: List[EventListener] = []

        self.log = logging.getLogger("picowave")
        self.log.setLevel(logging.DEBUG)
        self.log.handlers.clear()

        fh = logging.FileHandler(log_dir / "picowave.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self.log.addHandler(fh)

        ch = logging.StreamHandler(sys.stderr)
        ch.setLevel(logging.INFO if verbose else logging.WARNING)
        ch.setFormatter(logging.Formatter("%(message)s"))
        self.log.addHandler(ch)

        self.event("session_start", session_id=self.session_id)

    # -- listeners (e.g. the GUI console) ---------------------------------
    def add_listener(self, listener: EventListener) -> None:
        """Register a callback invoked as ``listener(stage, fields)`` per event."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: EventListener) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    # -- structured events -------------------------------------------------
    def event(self, stage: str, **fields: Any) -> None:
        """Append one JSON event to the session stream and mirror to the log."""
        record = {"ts": datetime.now().isoformat(timespec="seconds"),
                  "stage": stage, **fields}
        with open(self.jsonl_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        # Keep the console tidy: truncate long payloads.
        preview = {k: (v if not isinstance(v, str) or len(v) < 200
                       else v[:200] + "...") for k, v in fields.items()}
        self.log.debug("[%s] %s", stage, preview)
        # Notify any registered listeners (never let one break logging).
        for listener in list(self._listeners):
            try:
                listener(stage, dict(fields))
            except Exception:  # noqa: BLE001 - a bad listener must not crash logging
                self.log.exception("event listener failed for stage %s", stage)

    # -- convenience passthroughs -----------------------------------------
    def info(self, msg: str) -> None:  self.log.info(msg)
    def warn(self, msg: str) -> None:  self.log.warning(msg)
    def error(self, msg: str) -> None: self.log.error(msg)
    def debug(self, msg: str) -> None: self.log.debug(msg)


_singleton: Optional[SessionLogger] = None


def get_logger(log_dir: Optional[Path] = None, verbose: bool = True) -> SessionLogger:
    """Return the process-wide SessionLogger, creating it on first call."""
    global _singleton
    if _singleton is None:
        if log_dir is None:
            from .config import Config
            log_dir = Config().paths.logs
        _singleton = SessionLogger(log_dir, verbose=verbose)
    return _singleton
