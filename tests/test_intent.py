"""Tests for intent parsing, state merge and clamping.

Runnable with pytest, or directly:  python tests/test_intent.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from picowave.intent import Action, Intent, SessionState  # noqa: E402
from picowave.llm import MockLLM  # noqa: E402
from picowave.llm.prompts import build_intent_prompt, INTENT_SYSTEM_PROMPT  # noqa: E402


def _intent_for(text: str, state=None) -> Intent:
    state = state or SessionState()
    llm = MockLLM()
    raw = llm.generate(INTENT_SYSTEM_PROMPT, build_intent_prompt(text, state))
    return Intent.from_json(raw, raw_text=text)


def test_acquire_channel_b():
    it = _intent_for("acquire data from channel B")
    assert it.action == Action.ACQUIRE
    assert it.params.get("channel") == "B"


def test_siggen_frequency_khz():
    it = _intent_for("generate a 1 kHz sine wave")
    assert it.action == Action.SIGGEN
    assert it.params.get("siggen_freq_hz") == 1000
    assert it.params.get("siggen_wave") == "sine"


def test_set_trigger_level():
    it = _intent_for("set trigger level to 500 millivolts")
    assert it.action == Action.SET_PARAM
    assert it.params.get("trigger_level_mv") == 500
    assert it.params.get("trigger_enabled") is True


def test_arb_shape():
    it = _intent_for("generate an arbitrary sawtooth waveform")
    assert it.action == Action.ARB
    assert it.params.get("arb_shape") == "sawtooth"


def test_state_merge_and_clamp():
    s = SessionState()
    s.apply({"n_samples": 999999, "timebase": 99, "range_enum": "BOGUS"})
    assert s.n_samples == 32000           # clamped to max
    assert s.timebase == 23               # clamped to max
    assert s.range_enum == "PS2000_5V"    # invalid -> default


def test_intent_json_tolerates_fences():
    it = Intent.from_json('```json\n{"action":"exit","params":{}}\n```')
    assert it.action == Action.EXIT


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
