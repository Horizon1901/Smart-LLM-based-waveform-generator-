"""End-to-end orchestration.

    speech -> STT -> LLM intent -> merge into session state ->
    (if runnable) generate C -> compile -> [rollback+retry on failure] ->
    execute -> spoken result

Every stage is logged as a JSONL event. The compile/rollback/retry loop only
does real work in freeform mode; template mode compiles first-try by design.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .backup import BackupManager
from .codegen import CodeGenerator
from .codegen.freeform import FreeformGenerator
from .compiler import Compiler
from .config import Config
from .executor import Executor
from .gnuplot_export import PlotSpec, launch_gnuplot_multi
from .intent import Action, Intent, SessionState
from .llm.prompts import INTENT_SYSTEM_PROMPT, build_intent_prompt
from .logger import SessionLogger
from .measurements import find_csv_by_id, find_recent_csvs, measure_csv, summarize

# Exit codes the generated programs return on specific, known failure points
# (see templates/acquire.c.tmpl and templates/siggen.c.tmpl). Mapping these to
# plain language means a real device rejection is spoken clearly instead of
# the generic "the program ran but reported an error" -- check the console for
# the full stderr/stdout either way.
EXIT_CODE_MESSAGES = {
    99: "The PicoScope could not be opened. Check the USB cable, that the "
        "device isn't already in use by another program, and that it's "
        "powered and enumerated.",
    98: "That capture doesn't fit in one block on this device with the "
        "current channel selection. Try fewer samples, or a single channel "
        "instead of both.",
    97: "The device rejected these acquisition settings. Try a different "
        "sample count, timebase, or channel selection.",
    96: "The capture did not complete in time. Check the connection and try "
        "again.",
    95: "The device returned no data for that capture.",
    124: "The command took too long and was stopped before it finished. The "
         "device or the language model may be unresponsive.",
    126: "The compiled program could not be run.",
}


def _exit_code_message(returncode: Optional[int], fallback: str) -> str:
    if returncode is None:
        return fallback
    return EXIT_CODE_MESSAGES.get(returncode, fallback)


@dataclass
class CommandOutcome:
    text: str
    intent: Optional[Intent] = None
    action: str = ""
    spoken: str = ""
    generated_file: Optional[Path] = None
    csv_path: Optional[Path] = None
    compiled: bool = False
    executed: bool = False
    exit_code: Optional[int] = None
    errors: list = field(default_factory=list)
    should_exit: bool = False


class Pipeline:
    def __init__(self, cfg: Config, llm, logger: SessionLogger,
                 mode: str = "template"):
        self.cfg = cfg
        self.llm = llm
        self.log = logger
        self.mode = mode  # "template" | "llm-freeform"
        self.state = SessionState(
            n_samples=cfg.default_samples,
            timebase=cfg.default_timebase,
            range_enum=cfg.default_range_enum,
        )
        self.codegen = CodeGenerator(cfg.paths.templates, cfg.paths.generated)
        self.compiler = Compiler(cfg.compiler, cfg.paths)
        self.executor = Executor(cfg.paths.generated)
        self.backup = BackupManager(cfg.paths.backup)
        manufacturer_c = cfg.paths.manufacturer / "ps2000Con" / "ps2000Con.c"
        self.freeform = FreeformGenerator(
            llm, manufacturer_c, cfg.paths.generated, self.codegen.next_gen_id)

    # -- stage 1+2: recognised text -> intent -----------------------------
    def parse_intent(self, text: str) -> Intent:
        prompt = build_intent_prompt(text, self.state)
        self.log.event("llm_prompt", system=INTENT_SYSTEM_PROMPT, user=prompt)
        raw = self.llm.generate(INTENT_SYSTEM_PROMPT, prompt,
                                temperature=self.cfg.llm.temperature, force_json=True)
        self.log.event("llm_raw_reply", reply=raw)
        try:
            intent = Intent.from_json(raw, raw_text=text)
        except Exception as exc:  # noqa: BLE001
            intent = Intent(action=Action.UNKNOWN, raw_text=text,
                            notes=f"parse error: {exc}")
        self.log.event("intent", **intent.to_dict())
        return intent

    # -- build + run one runnable intent ----------------------------------
    def _generate(self, intent: Intent, temperature: float):
        if self.mode == "llm-freeform":
            return self.freeform.generate(intent, temperature=temperature)
        return self.codegen.generate(intent, self.state)

    def _build_and_run(self, intent: Intent, outcome: CommandOutcome) -> None:
        temperature = self.cfg.llm.temperature
        attempts = self.cfg.llm.max_retries if self.mode == "llm-freeform" else 1

        for attempt in range(1, attempts + 1):
            gen = self._generate(intent, temperature)
            outcome.generated_file = gen.path
            self.log.event("generated_code", attempt=attempt, path=str(gen.path),
                           template=gen.template, source=gen.path.read_text())

            # Backup before we depend on it, then compile.
            self.backup.snapshot(gen.path)
            comp = self.compiler.compile(gen.path)
            self.log.event("compile", attempt=attempt, ok=comp.ok,
                           command=comp.command, stdout=comp.stdout,
                           stderr=comp.stderr, returncode=comp.returncode)

            if comp.ok:
                self.backup.mark_good(gen.path)
                outcome.compiled = True
                ex = self.executor.run(comp.exe_path)
                self.log.event("execute", ok=ex.ok, returncode=ex.returncode,
                               stdout=ex.stdout, stderr=ex.stderr,
                               result_line=ex.result_line, device_ok=ex.device_ok)
                outcome.executed = ex.ok
                outcome.exit_code = ex.returncode
                csv_candidate = gen.path.with_suffix(".csv")
                if csv_candidate.exists():
                    outcome.csv_path = csv_candidate
                if not ex.device_ok:
                    outcome.spoken = _exit_code_message(
                        ex.returncode, "The PicoScope device could not be opened.")
                elif ex.result_line:
                    outcome.spoken = ex.result_line
                elif ex.ok:
                    outcome.spoken = "Command completed."
                else:
                    outcome.spoken = _exit_code_message(
                        ex.returncode, "The program ran but reported an error. "
                        "Check the console for details.")
                    outcome.errors.append(ex.stderr)
                # Housekeeping: keep the generated/ folder from growing forever.
                try:
                    self.codegen.prune_old(keep=self.cfg.max_generated_files)
                except Exception:  # noqa: BLE001 - cleanup must never break a run
                    pass
                return

            # Compile failed.
            outcome.errors.append(comp.stderr)
            first_error = _first_error_line(comp.stderr)
            self.log.warn(f"compile attempt {attempt} failed: {first_error}")
            if self.mode == "llm-freeform" and attempt < attempts:
                self.backup.restore(gen.path)  # rollback to last known-good
                temperature += self.cfg.llm.temperature_retry_step
                continue
            outcome.spoken = ("The generated program failed to compile. "
                              f"{first_error}")
            return

    # -- public: process one command --------------------------------------
    def process_command(self, text: str) -> CommandOutcome:
        self.log.event("recognized_text", text=text)
        outcome = CommandOutcome(text=text)
        if not text:
            outcome.spoken = "I did not catch that."
            return outcome

        intent = self.parse_intent(text)
        outcome.intent = intent
        outcome.action = intent.action.value

        if intent.action == Action.EXIT:
            outcome.should_exit = True
            outcome.spoken = "Shutting down."
            return outcome
        if intent.action == Action.HELP:
            outcome.spoken = _help_text()
            return outcome
        if intent.action == Action.UNKNOWN:
            outcome.spoken = "Sorry, I could not map that to a command."
            return outcome

        # Merge parameters into the persistent session state.
        self.state.apply(intent.params)
        self.log.event("state", **self.state.__dict__)

        if intent.action == Action.SET_PARAM:
            outcome.spoken = _describe_state(self.state)
            return outcome

        if intent.action == Action.PROCESS:
            self._handle_process(outcome, intent)
            return outcome

        # Runnable: acquire / siggen / arb / measure (generate+capture combined).
        self._build_and_run(intent, outcome)
        return outcome

    def _handle_process(self, outcome: CommandOutcome, intent: Intent) -> None:
        """Analyze + plot one or more recent captures. No hardware, no
        codegen/compile/execute -- operates purely on captures already on
        disk, so it works even across an app restart.

        Supports, via intent.params (not persisted to SessionState -- these
        are one-off analysis instructions, not device configuration):
          - process_files: list of 1-indexed ORDINAL positions, newest=1,
            next=2, ... (e.g. "process file 1 and file 2"). This is relative
            to "right now" -- it shifts as new captures are made, same as
            saying "my last two captures" in conversation. Defaults to [1].
          - process_capture_ids: list of LITERAL, stable capture IDs (e.g.
            "process acquisition 12") -- always the same file regardless of
            what else has been captured since, for when you already know the
            specific one you want (the response below always states the real
            ID of whatever it used, precisely so you can refer back to it
            this way later).
          - process_titles: list of per-file titles, matched positionally to
            the combined file list in the order given (ordinal refs first,
            then literal IDs).
          - plot_x_col / plot_y_col: a direct 1-indexed CSV column override,
            for "use column 1 and 3" style requests -- bypasses the default
            time-vs-mV channel plotting entirely, exactly like typing
            `using 1:3` into gnuplot by hand.
          - plot_style: "lines" (default) | "points" | "linespoints"/"lp".
        """
        file_refs = intent.params.get("process_files") or []
        capture_ids = intent.params.get("process_capture_ids") or []
        if not file_refs and not capture_ids:
            file_refs = [1]  # default: just the newest capture
        titles = intent.params.get("process_titles") or []
        x_col = intent.params.get("plot_x_col")
        y_col = intent.params.get("plot_y_col")
        style = intent.params.get("plot_style")

        csv_paths = []
        if file_refs:
            recent = find_recent_csvs(self.cfg.paths.generated, max(file_refs))
            if not recent:
                outcome.spoken = "No capture yet. Acquire some samples first."
                return
            for ref in file_refs:
                idx = ref - 1  # 1-indexed ordinal -> 0-indexed, newest first
                if 0 <= idx < len(recent):
                    csv_paths.append(recent[idx])
        for cid in capture_ids:
            found = find_csv_by_id(self.cfg.paths.generated, cid)
            if found is not None:
                csv_paths.append(found)

        if not csv_paths:
            available = len(find_recent_csvs(self.cfg.paths.generated, 9999))
            outcome.spoken = (
                f"Only {available} capture(s) available; couldn't resolve "
                f"the file(s) you asked for.")
            return

        outcome.csv_path = csv_paths[0]  # first referenced file, for the GUI's single-capture tabs
        summary_parts = []
        specs = []
        for i, csv_path in enumerate(csv_paths):
            title = titles[i] if i < len(titles) else None
            measurements = measure_csv(csv_path)
            # Always state the real, stable filename -- even when a title is
            # given -- so an ordinal reference that resolved to an
            # unexpected/older file is immediately visible instead of hiding
            # behind a title that looks right but points at the wrong data.
            label = f"{title} [{csv_path.stem}]" if title else csv_path.stem
            summary_parts.append(f"{label}: {summarize(measurements)}")
            channels = [m.channel for m in measurements]
            specs.append(PlotSpec(csv_path=csv_path, channels=channels, title=title))

        gnuplot_note = launch_gnuplot_multi(specs, x_col=x_col, y_col=y_col,
                                            style=style or "lines")
        summary = " | ".join(summary_parts)
        outcome.spoken = summary if not gnuplot_note else f"{summary} {gnuplot_note}"
        self.log.event("process", files=[str(p) for p in csv_paths],
                       titles=titles, x_col=x_col, y_col=y_col, style=style,
                       gnuplot_note=gnuplot_note)


# --- helpers ---------------------------------------------------------------
def _first_error_line(stderr: str) -> str:
    for line in stderr.splitlines():
        if "error:" in line:
            return line.strip()
    return (stderr.strip().splitlines() or ["unknown error"])[0]


def _describe_state(s: SessionState) -> str:
    channel_desc = "A and B" if s.channel == "BOTH" else s.channel
    return (f"Updated settings. Channel {channel_desc}, {s.n_samples} samples, "
            f"timebase {s.timebase}, trigger "
            f"{'on' if s.trigger_enabled else 'off'} at {s.trigger_level_mv} "
            f"millivolts {s.trigger_direction}, waveform {s.siggen_wave} at "
            f"{s.siggen_freq_hz} hertz.")


def _help_text() -> str:
    return ("You can say: acquire data from channel A, channel B, or both "
            "channels; generate a one kilohertz sine wave; generate a two "
            "kilohertz square wave; generate a triangle wave; generate a "
            "sine wave and capture it, to generate and measure in one step; "
            "process, to analyze and plot the most recent capture with "
            "gnuplot; set trigger level; set trigger type; set sample count; "
            "set timebase; generate an arbitrary waveform; set frequency, "
            "amplitude, or offset; increase or decrease amplitude, "
            "frequency, or offset. Say exit to quit.")
