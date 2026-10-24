"""Deterministic C generator.

Given an ``Intent`` and the current ``SessionState``, assembles a complete,
self-contained C program from the manufacturer-derived templates in
``templates/`` and writes it to ``generated/acquisition_NNN.c`` (monotonic id,
never overwritten). Because the templates only ever emit real ps2000 API calls,
the output always compiles against the (mock or real) SDK.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..intent import (Action, Intent, SessionState, WAVE_ENUM, RANGE_INDEX,
                      TRIGGER_DIR_ENUM)

# Input ranges in mV -- must match the C templates and the manufacturer example.
INPUT_RANGES_MV = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000, 50000]

# C snippets that compute one waveform period into y (-1..1) for the arb template.
ARB_SHAPE_BODY = {
    "sine":     "        y = sin(2.0 * M_PI * x);",
    "square":   "        y = (x < 0.5) ? 1.0 : -1.0;",
    "triangle": "        y = (x < 0.5) ? (4.0 * x - 1.0) : (3.0 - 4.0 * x);",
    "sawtooth": "        y = 2.0 * x - 1.0;",
}


@dataclass
class GenerationResult:
    gen_id: str          # zero-padded, e.g. "001"
    path: Path           # generated/acquisition_001.c
    action: Action
    template: str        # which template was used


def _mv_to_adc(mv: int, range_enum: str) -> int:
    full_scale_mv = INPUT_RANGES_MV[RANGE_INDEX[range_enum]]
    return int((mv * 32767) / full_scale_mv)


class CodeGenerator:
    def __init__(self, templates_dir: Path, generated_dir: Path):
        self.templates_dir = templates_dir
        self.generated_dir = generated_dir
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    # -- id management -----------------------------------------------------
    def next_gen_id(self) -> str:
        existing = []
        for p in self.generated_dir.glob("acquisition_*.c"):
            m = re.search(r"acquisition_(\d+)\.c$", p.name)
            if m:
                existing.append(int(m.group(1)))
        return f"{(max(existing) + 1) if existing else 1:03d}"

    def _load_template(self, name: str) -> str:
        return (self.templates_dir / name).read_text(encoding="utf-8")

    @staticmethod
    def _fill(template: str, subs: dict) -> str:
        out = template
        for key, val in subs.items():
            out = out.replace("{{" + key + "}}", str(val))
        return out

    @staticmethod
    def _intent_comment(intent: Intent) -> str:
        # Pretty JSON, safe inside a C block comment (no '*/' can appear in JSON).
        text = json.dumps(intent.to_dict(), indent=2)
        return "\n".join(" * " + line for line in text.splitlines())

    # -- action -> filled template ----------------------------------------
    def _render_acquire(self, gid: str, s: SessionState, intent: Intent) -> str:
        tmpl = self._load_template("acquire.c.tmpl")
        channel_sel = s.channel  # "A" | "B" | "BOTH"
        # Enable exactly the requested channel(s). On the 2000-series the block
        # buffer is shared across enabled channels, so a single channel gets the
        # whole buffer while BOTH halves the per-channel limit (SessionState
        # already caps n_samples accordingly for BOTH; the device itself is the
        # final authority and will refuse cleanly via get_timebase if not).
        ch_a_enabled = 1 if channel_sel in ("A", "BOTH") else 0
        ch_b_enabled = 1 if channel_sel in ("B", "BOTH") else 0

        if channel_sel == "BOTH":
            channel_desc = "channels A and B"
        else:
            channel_desc = f"channel {channel_sel}"

        # Print block: show the first PRINT_COUNT samples of every enabled
        # channel (built here, not at C runtime, since enablement is known now).
        # Values are resolved directly rather than nested as {{...}} tokens,
        # because this string is itself substituted into the template via a
        # single-pass replace -- a nested token here would never get filled.
        range_idx = RANGE_INDEX[s.range_enum]
        print_lines = []
        if ch_a_enabled:
            print_lines.append(
                '    printf("\\nFirst {{PRINT_COUNT}} samples of Channel A (mV):\\n");\n'
                "    for (i = 0; i < {{PRINT_COUNT}} && i < n_returned; i++)\n"
                f"        printf(\"  t=%d\\t%d mV\\n\", times[i], "
                f"adc_to_mv(values_a[i], {range_idx}));")
        if ch_b_enabled:
            print_lines.append(
                '    printf("\\nFirst {{PRINT_COUNT}} samples of Channel B (mV):\\n");\n'
                "    for (i = 0; i < {{PRINT_COUNT}} && i < n_returned; i++)\n"
                f"        printf(\"  t=%d\\t%d mV\\n\", times[i], "
                f"adc_to_mv(values_b[i], {range_idx}));")
        print_block = "\n".join(print_lines)

        if s.trigger_enabled:
            trig_channel = "A" if channel_sel != "B" else "B"
            src = "PS2000_CHANNEL_A" if trig_channel == "A" else "PS2000_CHANNEL_B"
            thr = _mv_to_adc(s.trigger_level_mv, s.range_enum)
            direction = TRIGGER_DIR_ENUM[s.trigger_direction]
            trigger_block = (
                f"    ps2000_set_trigger(handle, {src}, {thr}, {direction}, 0, 1000);\n"
                f'    printf("Trigger: {src} @ {s.trigger_level_mv} mV '
                f'({s.trigger_direction})\\n");'
            )
        else:
            trigger_block = (
                "    ps2000_set_trigger(handle, PS2000_NONE, 0, PS2000_RISING, 0, 1000);\n"
                '    printf("Trigger: disabled (immediate)\\n");'
            )

        subs = {
            "GEN_ID": gid,
            "TIMESTAMP": datetime.now().isoformat(timespec="seconds"),
            "COMMAND_TEXT": intent.raw_text.replace('"', "'"),
            "INTENT_JSON": self._intent_comment(intent),
            "OVERSAMPLE": s.oversample,
            "N_SAMPLES": s.n_samples,
            "TIMEBASE": s.timebase,
            "DC_COUPLED": s.dc_coupled,
            "RANGE_A_ENUM": s.range_enum,
            "RANGE_B_ENUM": s.range_enum,
            "RANGE_A_INDEX": RANGE_INDEX[s.range_enum],
            "RANGE_B_INDEX": RANGE_INDEX[s.range_enum],
            "CH_A_ENABLED": ch_a_enabled,
            "CH_B_ENABLED": ch_b_enabled,
            "TRIGGER_BLOCK": trigger_block,
            "PRINT_BLOCK": print_block,
            "CHANNEL_DESC": channel_desc,
            "PRINT_COUNT": min(10, s.n_samples),
        }
        return self._fill(tmpl, subs)

    def _render_siggen(self, gid: str, s: SessionState, intent: Intent) -> str:
        tmpl = self._load_template("siggen.c.tmpl")
        subs = {
            "GEN_ID": gid,
            "TIMESTAMP": datetime.now().isoformat(timespec="seconds"),
            "COMMAND_TEXT": intent.raw_text.replace('"', "'"),
            "INTENT_JSON": self._intent_comment(intent),
            "WAVE_ENUM": WAVE_ENUM[s.siggen_wave],
            "WAVE_NAME": s.siggen_wave,
            "FREQUENCY": s.siggen_freq_hz,
            "PKTOPK_UV": s.amplitude_mvpp * 1000,
            "OFFSET_UV": s.offset_mv * 1000,
            "HOLD_MS": s.hold_ms,
        }
        return self._fill(tmpl, subs)

    def _render_arb(self, gid: str, s: SessionState, intent: Intent) -> str:
        tmpl = self._load_template("arb.c.tmpl")
        subs = {
            "GEN_ID": gid,
            "TIMESTAMP": datetime.now().isoformat(timespec="seconds"),
            "COMMAND_TEXT": intent.raw_text.replace('"', "'"),
            "INTENT_JSON": self._intent_comment(intent),
            "WAVE_SIZE": 4096,
            "AWG_BUFFER_SIZE": 4096,
            "FREQUENCY": s.siggen_freq_hz,
            "OFFSET_UV": s.offset_mv * 1000,
            "PKTOPK_UV": s.amplitude_mvpp * 1000,
            "HOLD_MS": s.hold_ms,
            "ARB_SHAPE": s.arb_shape,
            "SHAPE_BODY": ARB_SHAPE_BODY.get(s.arb_shape, ARB_SHAPE_BODY["sine"]),
        }
        return self._fill(tmpl, subs)

    def _render_measure(self, gid: str, s: SessionState, intent: Intent) -> str:
        """Generate AND capture in one continuous device session (see
        measure.c.tmpl for why this exists instead of two separate commands).
        """
        tmpl = self._load_template("measure.c.tmpl")
        channel_sel = s.channel
        ch_a_enabled = 1 if channel_sel in ("A", "BOTH") else 0
        ch_b_enabled = 1 if channel_sel in ("B", "BOTH") else 0
        channel_desc = "channels A and B" if channel_sel == "BOTH" else f"channel {channel_sel}"

        range_idx = RANGE_INDEX[s.range_enum]
        print_lines = []
        if ch_a_enabled:
            print_lines.append(
                '    printf("\\nFirst {{PRINT_COUNT}} samples of Channel A (mV):\\n");\n'
                "    for (i = 0; i < {{PRINT_COUNT}} && i < n_returned; i++)\n"
                f"        printf(\"  t=%d\\t%d mV\\n\", times[i], "
                f"adc_to_mv(values_a[i], {range_idx}));")
        if ch_b_enabled:
            print_lines.append(
                '    printf("\\nFirst {{PRINT_COUNT}} samples of Channel B (mV):\\n");\n'
                "    for (i = 0; i < {{PRINT_COUNT}} && i < n_returned; i++)\n"
                f"        printf(\"  t=%d\\t%d mV\\n\", times[i], "
                f"adc_to_mv(values_b[i], {range_idx}));")
        print_block = "\n".join(print_lines)

        if s.trigger_enabled:
            trig_channel = "A" if channel_sel != "B" else "B"
            src = "PS2000_CHANNEL_A" if trig_channel == "A" else "PS2000_CHANNEL_B"
            thr = _mv_to_adc(s.trigger_level_mv, s.range_enum)
            direction = TRIGGER_DIR_ENUM[s.trigger_direction]
            trigger_block = (
                f"    ps2000_set_trigger(handle, {src}, {thr}, {direction}, 0, 1000);\n"
                f'    printf("Trigger: {src} @ {s.trigger_level_mv} mV '
                f'({s.trigger_direction})\\n");'
            )
        else:
            trigger_block = (
                "    ps2000_set_trigger(handle, PS2000_NONE, 0, PS2000_RISING, 0, 1000);\n"
                '    printf("Trigger: disabled (immediate)\\n");'
            )

        subs = {
            "GEN_ID": gid,
            "TIMESTAMP": datetime.now().isoformat(timespec="seconds"),
            "COMMAND_TEXT": intent.raw_text.replace('"', "'"),
            "INTENT_JSON": self._intent_comment(intent),
            "WAVE_ENUM": WAVE_ENUM[s.siggen_wave],
            "WAVE_NAME": s.siggen_wave,
            "FREQUENCY": s.siggen_freq_hz,
            "PKTOPK_UV": s.amplitude_mvpp * 1000,
            "OFFSET_UV": s.offset_mv * 1000,
            "OVERSAMPLE": s.oversample,
            "N_SAMPLES": s.n_samples,
            "TIMEBASE": s.timebase,
            "DC_COUPLED": s.dc_coupled,
            "RANGE_A_ENUM": s.range_enum,
            "RANGE_B_ENUM": s.range_enum,
            "RANGE_A_INDEX": range_idx,
            "RANGE_B_INDEX": range_idx,
            "CH_A_ENABLED": ch_a_enabled,
            "CH_B_ENABLED": ch_b_enabled,
            "TRIGGER_BLOCK": trigger_block,
            "PRINT_BLOCK": print_block,
            "CHANNEL_DESC": channel_desc,
            "PRINT_COUNT": min(10, s.n_samples),
        }
        return self._fill(tmpl, subs)

    # -- public entry point -----------------------------------------------
    def generate(self, intent: Intent, state: SessionState) -> GenerationResult:
        """Render + write a new generated C file for a runnable action."""
        gid = self.next_gen_id()
        if intent.action == Action.ACQUIRE:
            source, template = self._render_acquire(gid, state, intent), "acquire.c.tmpl"
        elif intent.action == Action.SIGGEN:
            source, template = self._render_siggen(gid, state, intent), "siggen.c.tmpl"
        elif intent.action == Action.ARB:
            source, template = self._render_arb(gid, state, intent), "arb.c.tmpl"
        elif intent.action == Action.MEASURE:
            source, template = self._render_measure(gid, state, intent), "measure.c.tmpl"
        else:
            raise ValueError(f"action {intent.action} is not a code-generating action")

        out_path = self.generated_dir / f"acquisition_{gid}.c"
        if out_path.exists():  # never overwrite -- bump until free
            gid = self.next_gen_id()
            out_path = self.generated_dir / f"acquisition_{gid}.c"
        out_path.write_text(source, encoding="utf-8")
        return GenerationResult(gen_id=gid, path=out_path,
                                action=intent.action, template=template)

    # -- housekeeping -------------------------------------------------------
    def prune_old(self, keep: int = 50) -> int:
        """Delete the oldest generated .c/.csv/.bin sets beyond ``keep``.

        Files are paired by their zero-padded id (acquisition_NNN.*). Returns
        the number of ids removed. Safe to call often; a no-op when under the
        limit.
        """
        ids = sorted({
            int(m.group(1))
            for p in self.generated_dir.glob("acquisition_*.c")
            if (m := re.search(r"acquisition_(\d+)\.c$", p.name))
        })
        overflow = ids[: max(0, len(ids) - keep)]
        for gid_int in overflow:
            gid = f"{gid_int:03d}"
            for pattern in (f"acquisition_{gid}.c", f"acquisition_{gid}.csv",
                            f"acquisition_{gid}"):
                target = self.generated_dir / pattern
                if target.exists() and target.is_file():
                    target.unlink()
        return len(overflow)
