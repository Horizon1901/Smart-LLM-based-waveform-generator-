"""Persist GUI settings (SDK mode, LLM choice, session parameters) across runs.

Stored as plain JSON next to the project's other runtime state. Loading is
best-effort: any error (missing file, corrupt JSON, unknown field) is treated
as "nothing to restore" rather than a crash, since a fresh default state is
always a safe fallback.
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict, fields
from pathlib import Path
from typing import Any, Optional

from ..intent import SessionState

log = logging.getLogger("picowave.gui.settings")


def settings_path(cfg) -> Path:
    return cfg.paths.root / "config" / "gui_settings.json"


def save_settings(cfg, state: SessionState, sdk_mode: str, llm_choice: str) -> None:
    payload = {
        "sdk_mode": sdk_mode,
        "llm_choice": llm_choice,
        "session_state": asdict(state),
    }
    path = settings_path(cfg)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except OSError as exc:  # noqa: BLE001 - never block shutdown on this
        log.warning("could not save GUI settings: %s", exc)


def load_settings(cfg) -> Optional[dict]:
    path = settings_path(cfg)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        log.warning("could not load GUI settings (%s), using defaults", exc)
        return None


def apply_session_state(state: SessionState, saved: dict) -> None:
    """Copy known fields from a saved dict onto a live SessionState in place."""
    valid = {f.name for f in fields(SessionState)}
    for key, value in saved.items():
        if key in valid:
            setattr(state, key, value)
    state.clamp()
