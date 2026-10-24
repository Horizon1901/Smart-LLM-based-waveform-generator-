"""Bridge backend logging + SessionLogger events into Qt signals.

The console subscribes to :class:`LogBridge.message`. Two sources feed it:
  * a stdlib ``logging.Handler`` attached to the "picowave" logger, and
  * a :class:`SessionLogger` listener that formats structured stage events.

Emissions may occur on a worker thread; because the bridge lives in the GUI
thread, the queued signal delivery marshals them safely onto the UI thread.
"""
from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal


class LogBridge(QObject):
    # (level, text) -- level in {"debug","info","warning","error","stage"}
    message = Signal(str, str)

    def __init__(self) -> None:
        super().__init__()

    # -- SessionLogger listener (structured stage events) -----------------
    def on_event(self, stage: str, fields: dict) -> None:
        summary = self._summarise(stage, fields)
        self.message.emit("stage", f"[{stage}] {summary}")

    @staticmethod
    def _summarise(stage: str, fields: dict) -> str:
        keys_by_stage = {
            "intent": ("action", "confidence"),
            "state": ("channel", "n_samples", "siggen_wave", "siggen_freq_hz",
                      "amplitude_mvpp"),
            "generated_code": ("template", "path"),
            "compile": ("ok", "returncode"),
            "execute": ("ok", "returncode", "result_line"),
            "recognized_text": ("text",),
        }
        wanted = keys_by_stage.get(stage)
        items = ((k, fields[k]) for k in wanted if k in fields) if wanted \
            else fields.items()
        parts = []
        for k, v in items:
            s = str(v)
            if len(s) > 80:
                s = s[:80] + "..."
            parts.append(f"{k}={s}")
        return " ".join(parts)


class QtLogHandler(logging.Handler):
    """Forwards stdlib log records to a :class:`LogBridge`."""

    def __init__(self, bridge: LogBridge) -> None:
        super().__init__()
        self._bridge = bridge

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = record.levelname.lower()
            self._bridge.message.emit(level, record.getMessage())
        except Exception:  # never let logging raise into the app
            pass


def install_console_bridge(bridge: LogBridge, session_logger,
                           level: int = logging.INFO) -> Optional[QtLogHandler]:
    """Wire both feeds. Returns the installed handler (for later removal)."""
    session_logger.add_listener(bridge.on_event)
    handler = QtLogHandler(bridge)
    handler.setLevel(level)
    logging.getLogger("picowave").addHandler(handler)
    return handler
