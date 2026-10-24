"""Local LLM clients.

``OllamaClient`` talks to a local Ollama server over HTTP using only the standard
library (urllib) so there is no hard third-party dependency. ``MockLLM`` is a
deterministic, rule-based stand-in that produces the same JSON contract, letting
the whole pipeline run and be tested with no model server present -- including
the relative-adjustment commands ("increase amplitude", "decrease frequency").
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Dict, Optional


class LLMError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, host: str, model: str, timeout_s: int = 120):
        self.host = host.rstrip("/")
        self.model = model
        self.timeout_s = timeout_s

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.host}/api/tags")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(self, system: str, prompt: str, temperature: float = 0.0,
                 force_json: bool = True) -> str:
        """One-shot completion via Ollama /api/generate."""
        payload = {
            "model": self.model,
            "system": system,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": float(temperature)},
        }
        if force_json:
            payload["format"] = "json"  # Ollama-native JSON mode
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/generate", data=data,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise LLMError(f"Ollama request failed: {exc}") from exc
        return body.get("response", "")


class MockLLM:
    """Rule-based intent extractor with the same JSON output contract.

    Not a language model -- a small deterministic parser so the pipeline works
    offline with no Ollama. Good enough for the fixed command vocabulary,
    including relative adjustments emitted as op objects.
    """

    _NUM = re.compile(r"(-?\d+(?:\.\d+)?)")

    # Direction vocabulary for relative adjustments.
    _UP = ("increase", "raise", "boost", "turn up", "higher", "more", "bump", "up ")
    _DOWN = ("decrease", "lower", "reduce", "turn down", "drop", "less", "down ")

    # Field keyword -> session field. Order matters: check "trigger level"
    # before bare amplitude wording so they don't collide.
    _FIELD_WORDS = (
        ("trigger_level_mv", ("trigger level", "trigger threshold")),
        ("amplitude_mvpp", ("amplitude", "vpp", "peak to peak", "peak-to-peak")),
        ("siggen_freq_hz", ("frequency", "freq")),
        ("offset_mv", ("offset",)),
        ("n_samples", ("sample",)),
        ("timebase", ("timebase", "time base")),
    )

    def available(self) -> bool:
        return True

    def _freq_hz(self, text: str) -> Optional[int]:
        m = re.search(r"(\d+(?:\.\d+)?)\s*(k?)\s*hz", text)
        if not m:
            return None
        val = float(m.group(1)) * (1000 if m.group(2) == "k" else 1)
        return int(val)

    def _by_amount(self, text: str, field: str) -> Optional[int]:
        """Extract 'by N <unit>' magnitude, unit-aware for the given field."""
        m = re.search(r"by\s+(\d+(?:\.\d+)?)\s*(k?)\s*"
                      r"(hz|hertz|mv|millivolts?|v|volts?|samples?)?", text)
        if not m:
            return None
        val = float(m.group(1))
        kilo = m.group(2) == "k"
        unit = m.group(3) or ""
        if field == "siggen_freq_hz":
            return int(val * (1000 if kilo else 1))
        if unit in ("v", "volt", "volts"):
            return int(val * 1000)  # volts -> mV
        return int(val * (1000 if kilo else 1))

    def _relative_ops(self, text: str) -> Dict[str, dict]:
        """Detect relative adjustments and return {field: op_object}."""
        ops: Dict[str, dict] = {}
        up = any(w in text for w in self._UP)
        down = any(w in text for w in self._DOWN)
        is_double = "double" in text or "twice" in text
        is_halve = "halve" in text or "half " in text or "in half" in text

        pct_match = (re.search(r"by\s+(\d+(?:\.\d+)?)\s*(?:percent|%)", text)
                     or re.search(r"(\d+(?:\.\d+)?)\s*(?:percent|%)", text))
        pct = float(pct_match.group(1)) if pct_match else None

        for field, words in self._FIELD_WORDS:
            if not any(w in text for w in words):
                continue
            if is_double:
                ops[field] = {"op": "mul", "factor": 2}
                continue
            if is_halve:
                ops[field] = {"op": "mul", "factor": 0.5}
                continue
            if not (up or down):
                continue
            op: dict = {"op": "inc" if (up and not down) else "dec"}
            if pct is not None:
                op["pct"] = pct
            else:
                by = self._by_amount(text, field)
                if by is not None:
                    op["by"] = by
            ops[field] = op
        return ops

    def _parse_process_extras(self, text: str) -> dict:
        """Extract "process"-specific params: which file(s), per-file titles,
        and an optional verbal gnuplot column/style override -- the offline
        equivalent of what the real LLM does via the prompt schema.
        """
        extras: dict = {}

        # File references: "file 1 and file 2", "files 1 and 2", "file 1, 2".
        file_nums = [int(n) for n in re.findall(r"file\s*(\d+)", text)]
        if not file_nums:
            m = re.search(r"files?\s+(\d+)\s*(?:,|and)\s*(\d+)"
                          r"(?:\s*(?:,|and)\s*(\d+))?", text)
            if m:
                file_nums = [int(g) for g in m.groups() if g]
        if file_nums:
            extras["process_files"] = file_nums

        # Literal, stable capture-ID references: "acquisition 12",
        # "capture number 12", "capture id 12" -- distinct wording from
        # "file N" (ordinal) so both can be said unambiguously.
        capture_ids = [int(n) for n in re.findall(
            r"(?:acquisition|capture(?:\s+(?:number|id))?)\s*#?\s*(\d+)", text)]
        if capture_ids:
            extras["process_capture_ids"] = capture_ids

        # Titles: "title it X" (single), "titled X and Y", "title as X, Y, Z".
        m = re.search(
            r"titles?\s*(?:as|it|them|:)?\s+([a-z0-9_\-]+)"
            r"(?:\s*(?:,|and)\s*([a-z0-9_\-]+))?"
            r"(?:\s*(?:,|and)\s*([a-z0-9_\-]+))?", text)
        if m:
            extras["process_titles"] = [g for g in m.groups() if g]

        # Column override: "column 1 and 3", "use column 1 and 3", "using 1 and 3".
        m = (re.search(r"columns?\s+(\d+)\s*(?:and|,)\s*(\d+)", text)
            or re.search(r"us(?:e|ing)\s+(?:column\s+)?(\d+)\s*(?:and|,)\s*(\d+)", text))
        if m:
            extras["plot_x_col"] = int(m.group(1))
            extras["plot_y_col"] = int(m.group(2))

        # Style: "with lines" / "with points" / "with lp" / "with linespoints".
        m = re.search(r"with\s+(lines?|points?|linespoints|lp)\b", text)
        if m:
            extras["plot_style"] = m.group(1)

        return extras

    def generate(self, system: str, prompt: str, temperature: float = 0.0,
                 force_json: bool = True) -> str:
        # The user utterance is embedded in the prompt as: User request: "..."
        m = re.search(r'request:\s*"(.*?)"', prompt, re.IGNORECASE | re.DOTALL)
        text = (m.group(1) if m else prompt).lower()
        params: dict = {}
        action = "unknown"

        # --- relative adjustments first (they take precedence over absolute) --
        relative = self._relative_ops(text)
        rel_fields = set(relative)
        params.update(relative)
        if relative:
            action = "set_param"

        if any(w in text for w in ("exit", "quit", "stop the program", "goodbye")):
            action = "exit"
        elif "help" in text or "what can you" in text:
            action = "help"
        elif any(w in text for w in ("process", "analyze", "analyse",
                                     "show the results", "show me the output",
                                     "plot it")):
            action = "process"
            params.update(self._parse_process_extras(text))
        elif (any(g in text for g in ("generate", "output", "wave"))
              and any(c in text for c in ("capture", "measure", "acquire",
                                          "loopback", "verify"))):
            # Combined request: generate AND capture in one guaranteed-live
            # session (see measure.c.tmpl -- separate siggen+acquire commands
            # can't work because the signal is already gone by the time
            # "generate" returns control).
            action = "measure"
            for name in ("sine", "square", "triangle"):
                if name in text:
                    params["siggen_wave"] = name
            if "ramp up" in text:
                params["siggen_wave"] = "ramp_up"
            elif "ramp down" in text:
                params["siggen_wave"] = "ramp_down"
            f = self._freq_hz(text)
            if f and "siggen_freq_hz" not in rel_fields:
                params["siggen_freq_hz"] = f
            if re.search(r"both channels|channel a and b|channels a and b|"
                        r"a and b\b|both inputs", text):
                params["channel"] = "BOTH"
            elif re.search(r"channel\s*b\b", text):
                params["channel"] = "B"
            elif re.search(r"channel\s*a\b", text):
                params["channel"] = "A"
        elif any(w in text for w in ("arbitrary", "custom wave")):
            action = "arb"
            for shape in ("sine", "square", "triangle", "sawtooth"):
                if shape in text:
                    params["arb_shape"] = shape
            f = self._freq_hz(text)
            if f and "siggen_freq_hz" not in rel_fields:
                params["siggen_freq_hz"] = f
        elif any(w in text for w in ("generate", "output", "sig gen", "signal generator", "wave")):
            action = "siggen"
            for name in ("sine", "square", "triangle"):
                if name in text:
                    params["siggen_wave"] = name
            if "ramp up" in text:
                params["siggen_wave"] = "ramp_up"
            elif "ramp down" in text:
                params["siggen_wave"] = "ramp_down"
            f = self._freq_hz(text)
            if f and "siggen_freq_hz" not in rel_fields:
                params["siggen_freq_hz"] = f
        elif any(w in text for w in ("acquire", "capture", "read", "collect", "sample data")):
            action = "acquire"
            if re.search(r"both channels|channel a and b|channels a and b|"
                        r"a and b\b|both inputs", text):
                params["channel"] = "BOTH"
            elif re.search(r"channel\s*b|\bb\b", text):
                params["channel"] = "B"
            elif re.search(r"channel\s*a|\ba\b", text):
                params["channel"] = "A"

        # set_param style utterances (may also refine an action above). Each
        # absolute branch is skipped if that field was already set relatively.
        if ("trigger level" in text or ("trigger" in text and "level" in text)) \
                and "trigger_level_mv" not in rel_fields:
            n = self._NUM.search(text)
            if n:
                params["trigger_level_mv"] = int(float(n.group(1)))
                params["trigger_enabled"] = True
                if action == "unknown":
                    action = "set_param"
        if "trigger type" in text or "rising" in text or "falling" in text:
            params["trigger_direction"] = "falling" if "falling" in text else "rising"
            params["trigger_enabled"] = True
            if action == "unknown":
                action = "set_param"
        if ("sample count" in text or "samples" in text) \
                and "n_samples" not in rel_fields:
            n = self._NUM.search(text)
            if n:
                params["n_samples"] = int(float(n.group(1)))
                if action == "unknown":
                    action = "set_param"
        if "timebase" in text and "timebase" not in rel_fields:
            n = self._NUM.search(text)
            if n:
                params["timebase"] = int(float(n.group(1)))
                if action == "unknown":
                    action = "set_param"
        if "amplitude" in text and "amplitude_mvpp" not in rel_fields:
            n = self._NUM.search(text)
            if n:
                params["amplitude_mvpp"] = int(float(n.group(1)))
                if action == "unknown":
                    action = "set_param"
        if "offset" in text and "offset_mv" not in rel_fields:
            n = self._NUM.search(text)
            if n:
                params["offset_mv"] = int(float(n.group(1)))
                if action == "unknown":
                    action = "set_param"
        if action in ("set_param", "unknown") and "frequency" in text \
                and "siggen_freq_hz" not in rel_fields:
            f = self._freq_hz(text) or (int(float(self._NUM.search(text).group(1)))
                                        if self._NUM.search(text) else None)
            if f:
                params["siggen_freq_hz"] = f
                action = "set_param" if action == "unknown" else action

        # "hold the output for 20 seconds" / "keep the signal on for a minute"
        hold_match = re.search(
            r"(?:hold|keep).{0,20}?(?:for\s+)?(\d+(?:\.\d+)?)\s*"
            r"(sec(?:ond)?s?|min(?:ute)?s?|ms|milliseconds?)", text)
        if hold_match:
            val = float(hold_match.group(1))
            unit = hold_match.group(2)
            if unit.startswith("min"):
                ms = int(val * 60_000)
            elif unit == "ms" or unit.startswith("milli"):
                ms = int(val)
            else:
                ms = int(val * 1000)
            params["hold_ms"] = ms
            if action == "unknown":
                action = "set_param"
        elif re.search(r"(?:hold|keep).{0,10}(?:on\s+)?(?:for\s+)?a\s+minute", text):
            params["hold_ms"] = 60_000
            if action == "unknown":
                action = "set_param"

        return json.dumps({
            "action": action,
            "params": params,
            "confidence": 0.9 if action != "unknown" else 0.2,
            "notes": "mock-rule-based",
        })
