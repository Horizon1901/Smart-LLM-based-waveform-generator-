"""Intent schema and session state for PicoWave Assistant.

The LLM's only structured job is to turn recognised speech into an ``Intent``:
an ``action`` plus a ``params`` dict. Parameters are merged into a persistent
``SessionState`` (so "set trigger level to 500 mV" then "acquire channel A"
works), then validated/clamped before code generation. Adding a new command is
a matter of adding an action + a few params + a template -- nothing else.

Parameter values are normally *absolute* scalars (``"amplitude_mvpp": 3000``).
As of the relative-command extension a value may instead be a *relative op
object* -- ``{"op": "inc"}``, ``{"op": "dec", "by": 500}``, ``{"op": "inc",
"pct": 20}`` or ``{"op": "mul", "factor": 2}`` -- which adjusts the field
relative to its current value. Absolute commands are unchanged; relative ops are
handled by a separate branch in :meth:`SessionState.apply`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional


class Action(str, Enum):
    ACQUIRE = "acquire"       # capture a block from a channel
    SIGGEN = "siggen"         # built-in waveform
    ARB = "arb"               # arbitrary waveform
    MEASURE = "measure"       # generate a waveform AND capture it, one session
    PROCESS = "process"       # analyze + plot the most recent capture (gnuplot + built-in)
    SET_PARAM = "set_param"   # mutate session state only (no run)
    HELP = "help"
    EXIT = "exit"
    UNKNOWN = "unknown"


# Wave name (lowercase) -> PicoSDK enum symbol used in generated C.
WAVE_ENUM = {
    "sine": "PS2000_SINE",
    "square": "PS2000_SQUARE",
    "triangle": "PS2000_TRIANGLE",
    "ramp_up": "PS2000_RAMPUP",
    "ramp_down": "PS2000_RAMPDOWN",
}

# Range enum symbol -> index into input_ranges[] (for adc_to_mv scaling).
RANGE_INDEX = {
    "PS2000_10MV": 0, "PS2000_20MV": 1, "PS2000_50MV": 2, "PS2000_100MV": 3,
    "PS2000_200MV": 4, "PS2000_500MV": 5, "PS2000_1V": 6, "PS2000_2V": 7,
    "PS2000_5V": 8, "PS2000_10V": 9, "PS2000_20V": 10, "PS2000_50V": 11,
}

TRIGGER_DIR_ENUM = {"rising": "PS2000_RISING", "falling": "PS2000_FALLING"}


# --------------------------------------------------------------------------- #
# Relative-adjustment support ("increase amplitude", "decrease frequency", ...).
#
# Numeric fields that accept a relative op object. Non-numeric fields (channel,
# waveform, range, direction) are absolute-only.
# --------------------------------------------------------------------------- #
_RELATIVE_FIELDS = {
    "n_samples", "timebase", "oversample", "trigger_level_mv",
    "siggen_freq_hz", "amplitude_mvpp", "offset_mv",
}

# Direction-only default step per field, as (kind, magnitude):
#   "add" -> add/subtract <magnitude> in the field's own unit
#   "pct" -> add/subtract <magnitude> percent of the current value
#   "mul" -> multiply by <magnitude> (up) or divide by it (down)
_REL_DEFAULTS: Dict[str, tuple] = {
    "amplitude_mvpp": ("add", 200),
    "offset_mv": ("add", 200),
    "siggen_freq_hz": ("pct", 25),
    "n_samples": ("mul", 2),
    "timebase": ("add", 1),
    "trigger_level_mv": ("add", 100),
    "oversample": ("add", 1),
}

_INC_WORDS = {"inc", "increase", "up", "raise", "higher", "more", "boost"}
_DEC_WORDS = {"dec", "decrease", "down", "lower", "reduce", "less", "drop"}


def _num(value: Any) -> Optional[float]:
    """Best-effort numeric coercion; returns None if not a number."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class SessionState:
    """Everything a generated program needs. Mutated by successive commands."""
    channel: str = "A"                 # "A" or "B" (which channel to report)
    range_enum: str = "PS2000_5V"      # input range for both channels
    dc_coupled: int = 1                # 1 = DC, 0 = AC
    n_samples: int = 1024
    timebase: int = 8
    oversample: int = 1

    trigger_enabled: bool = False
    trigger_level_mv: int = 0
    trigger_direction: str = "rising"  # "rising" | "falling"

    # Signal generator (built-in + arbitrary share amplitude/offset/frequency).
    siggen_wave: str = "sine"
    siggen_freq_hz: int = 1000
    amplitude_mvpp: int = 2000         # peak-to-peak, mV
    offset_mv: int = 0
    arb_shape: str = "sine"
    hold_ms: int = 8000

    def clamp(self) -> None:
        """Keep every field inside device-safe bounds."""
        ch = str(self.channel).upper()
        if ch in ("BOTH", "AB", "A+B", "A,B", "A AND B"):
            self.channel = "BOTH"
        elif ch.endswith("B"):
            self.channel = "B"
        else:
            self.channel = "A"
        if self.range_enum not in RANGE_INDEX:
            self.range_enum = "PS2000_5V"
        self.dc_coupled = 1 if self.dc_coupled else 0
        self.n_samples = int(max(16, min(self.n_samples, 32000)))
        # Both channels share one block buffer, so the per-channel ceiling is
        # roughly half of the single-channel max. Cap proactively so a dual-
        # channel request doesn't routinely land on the device's own refusal
        # (exit 98) -- the device is still the final authority if this estimate
        # is optimistic for a given unit.
        if self.channel == "BOTH":
            self.n_samples = min(self.n_samples, 4000)
        self.timebase = int(max(0, min(self.timebase, 23)))
        self.oversample = int(max(1, min(self.oversample, 256)))
        self.trigger_direction = (self.trigger_direction
                                  if self.trigger_direction in TRIGGER_DIR_ENUM else "rising")
        self.trigger_level_mv = int(max(-20000, min(self.trigger_level_mv, 20000)))
        if self.siggen_wave not in WAVE_ENUM:
            self.siggen_wave = "sine"
        self.siggen_freq_hz = int(max(1, min(self.siggen_freq_hz, 100000)))
        self.amplitude_mvpp = int(max(0, min(self.amplitude_mvpp, 4000)))  # +/-2V
        self.offset_mv = int(max(-2000, min(self.offset_mv, 2000)))
        if self.arb_shape not in ("sine", "square", "triangle", "sawtooth"):
            self.arb_shape = "sine"
        self.hold_ms = int(max(0, min(self.hold_ms, 60000)))

    def apply(self, params: Dict[str, Any]) -> None:
        """Overlay a params dict from an Intent, ignoring unknown keys.

        A scalar value sets the field absolutely (existing behaviour). A dict
        value is a relative op object and adjusts the field relative to its
        current value (new behaviour).
        """
        for key, value in params.items():
            if value is None or not hasattr(self, key):
                continue
            if isinstance(value, dict):
                self._apply_relative(key, value)
            else:
                setattr(self, key, value)
        self.clamp()

    def _apply_relative(self, field_name: str, op: Dict[str, Any]) -> None:
        """Adjust one numeric field relative to its current value."""
        if field_name not in _RELATIVE_FIELDS:
            return  # relative ops only apply to numeric fields
        current = _num(getattr(self, field_name))
        if current is None:
            return

        opname = str(op.get("op", "")).strip().lower()

        # Multiplicative: {"op": "mul", "factor": 2}  (also "scale").
        if opname in ("mul", "scale"):
            factor = _num(op.get("factor"))
            if factor is None:
                return
            setattr(self, field_name, int(round(current * factor)))
            return

        # Absolute via op form (defensive): {"op": "set", "value": N}.
        if opname in ("set", "assign"):
            value = _num(op.get("value"))
            if value is not None:
                setattr(self, field_name, int(round(value)))
            return

        # Additive up/down.
        if opname in _INC_WORDS:
            sign = 1.0
        elif opname in _DEC_WORDS:
            sign = -1.0
        else:
            return  # unrecognised op -> leave field untouched

        by = _num(op.get("by"))
        pct = _num(op.get("pct"))
        if by is not None:
            delta = abs(by)
        elif pct is not None:
            delta = abs(current) * abs(pct) / 100.0
        else:
            kind, mag = _REL_DEFAULTS.get(field_name, ("add", 1))
            if kind == "pct":
                delta = abs(current) * float(mag) / 100.0
            elif kind == "mul":
                # Direction-only multiplicative default (e.g. samples: double/halve).
                new_mul = current * float(mag) if sign > 0 else current / float(mag)
                setattr(self, field_name, int(round(new_mul)))
                return
            else:  # "add"
                delta = float(mag)

        # Guarantee a visible change for integer fields.
        if int(round(delta)) == 0:
            delta = 1.0
        setattr(self, field_name, int(round(current + sign * delta)))


@dataclass
class Intent:
    action: Action = Action.UNKNOWN
    params: Dict[str, Any] = field(default_factory=dict)
    raw_text: str = ""
    confidence: float = 0.0
    notes: str = ""

    @staticmethod
    def from_json(text: str, raw_text: str = "") -> "Intent":
        """Parse an LLM JSON reply into an Intent, tolerating code fences."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:]
        # Grab the outermost {...} to survive stray prose.
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start == -1 or end == -1:
            return Intent(action=Action.UNKNOWN, raw_text=raw_text,
                          notes="no JSON object found in LLM reply")
        obj = json.loads(cleaned[start:end + 1])
        try:
            action = Action(str(obj.get("action", "unknown")).lower())
        except ValueError:
            action = Action.UNKNOWN
        return Intent(
            action=action,
            params=obj.get("params", {}) or {},
            raw_text=raw_text,
            confidence=float(obj.get("confidence", 0.0) or 0.0),
            notes=str(obj.get("notes", "")),
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["action"] = self.action.value
        return d
