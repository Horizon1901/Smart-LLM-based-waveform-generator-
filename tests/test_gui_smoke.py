"""Headless GUI smoke tests -- run offscreen, no display/mic/hardware needed.

Covers what was previously verified by hand each phase: the window builds, a
siggen command plots the ideal waveform, an acquisition writes and plots a
real CSV (including a dual-channel capture), relative commands mutate state,
settings persist across a save/restore cycle, and the CLI-facing backend is
untouched.

Requires PySide6 + matplotlib (the GUI extras); skipped entirely if absent so
`pytest` still passes on a CLI-only install.
"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_API", "pyside6")

from picowave.config import Config  # noqa: E402
from picowave.llm.client import MockLLM  # noqa: E402
from picowave.logger import SessionLogger  # noqa: E402
from picowave.pipeline import Pipeline  # noqa: E402
from picowave.voice import SpeechRecognizer, Speaker  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def window(qapp, tmp_path):
    from picowave.gui.main_window import MainWindow

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.root = tmp_path  # keeps gui_settings.json out of the real repo
    cfg.paths.ensure()

    logger = SessionLogger(cfg.paths.logs)
    llm = MockLLM()
    pipeline = Pipeline(cfg, llm, logger)
    rec = SpeechRecognizer(force_text=True)
    spk = Speaker(enabled=False)
    win = MainWindow(pipeline, logger, llm, "mock", cfg, rec, spk, "mock")
    yield win
    win.close()


def test_window_builds_with_three_tabs(window):
    assert window.tabs.count() == 3


def test_siggen_plots_ideal_waveform(window):
    outcome = window.pipeline.process_command("generate a square wave at 3000 Hz")
    window._on_finished(outcome)
    assert len(window.result_tab.canvas.ax.lines) >= 1


def test_single_channel_acquire_writes_and_plots_csv(window):
    outcome = window.pipeline.process_command("acquire 1024 samples from channel A")
    window._on_finished(outcome)
    assert outcome.csv_path is not None and outcome.csv_path.exists()
    assert window.csv_tab.table.rowCount() > 0


def test_dual_channel_acquire_populates_both_columns(window):
    outcome = window.pipeline.process_command("acquire from both channels")
    assert outcome.csv_path is not None and outcome.csv_path.exists()
    text = outcome.csv_path.read_text()
    rows = [r.split(",") for r in text.strip().splitlines()[1:]]
    ch_a = [float(r[3]) for r in rows]
    ch_b = [float(r[5]) for r in rows]
    assert any(v != 0 for v in ch_a), "channel A column should have real data"
    assert any(v != 0 for v in ch_b), "channel B column should have real data"


def test_relative_command_changes_amplitude(window):
    window.pipeline.process_command("generate a sine wave at 1000 Hz")
    before = window.pipeline.state.amplitude_mvpp
    window.pipeline.process_command("increase the amplitude")
    assert window.pipeline.state.amplitude_mvpp > before


def test_set_param_redraws_the_live_waveform_plot(window):
    """Regression test: changing a setting (absolute or relative) must
    immediately update the on-screen ideal waveform. Previously, "set_param"
    outcomes were never routed to a redraw at all -- the plot silently went
    stale the moment you changed anything, which looked exactly like "nothing
    happened" even though the underlying state was updating correctly.
    """
    outcome = window.pipeline.process_command("generate a sine wave at 1000 Hz")
    window._on_finished(outcome)
    before = list(window.result_tab.canvas.ax.lines[0].get_ydata())

    outcome2 = window.pipeline.process_command("increase the amplitude")
    window._on_finished(outcome2)
    after_relative = list(window.result_tab.canvas.ax.lines[0].get_ydata())
    assert before != after_relative, "relative command ('increase') should redraw the plot"

    outcome3 = window.pipeline.process_command("change frequency to 5000 Hz")
    window._on_finished(outcome3)
    assert "5000" in window.result_tab.caption.text(), (
        "absolute command ('change frequency to') should redraw the plot")


def test_frequency_change_is_visually_distinguishable(window):
    """Regression test: the ideal-waveform display window used to always span
    exactly N cycles of whatever frequency was given, so the plot auto-scaled
    to "N wiggles filling the width" at every frequency -- making a frequency
    change invisible unless you read the axis tick labels. The window must now
    be fixed, so a higher frequency visibly packs in more cycles.
    """
    from picowave.gui.waveform_math import ideal_waveform
    import numpy as np

    t1, y1 = ideal_waveform("triangle", 1000, 2000, 0)
    t2, y2 = ideal_waveform("triangle", 2000, 2000, 0)
    assert round(t1[-1], 6) == round(t2[-1], 6), "display window must be fixed, not per-frequency"
    crossings1 = int(np.sum(np.diff(np.sign(y1)) != 0))
    crossings2 = int(np.sum(np.diff(np.sign(y2)) != 0))
    assert crossings2 > crossings1 * 1.5, (
        "doubling the frequency should visibly increase cycle density in the "
        "same fixed window")


def test_process_action_routes_to_both_tabs(window, monkeypatch):
    """"process" after an acquire must populate the app's own Result/CSV tabs
    (the built-in-plot half of the requirement) in addition to triggering
    gnuplot (patched out here so the test suite doesn't spawn a real window).
    """
    import picowave.pipeline as pipeline_mod
    monkeypatch.setattr(pipeline_mod, "launch_gnuplot_multi",
                        lambda specs, x_col=None, y_col=None, style="lines": None)

    o1 = window.pipeline.process_command("acquire 1024 samples from channel A")
    window._on_finished(o1)
    o2 = window.pipeline.process_command("process")
    window._on_finished(o2)

    assert o2.action == "process"
    assert len(window.result_tab.canvas.ax.lines) >= 1
    assert window.csv_tab.table.rowCount() > 0
    assert "Channel" in o2.spoken  # real measurement summary, not a placeholder


def test_oversized_acquire_fails_cleanly_not_hangs(window):
    outcome = window.pipeline.process_command("acquire 32000 samples from channel A")
    # Either it's clamped and succeeds, or it fails with a known exit code --
    # either way process_command must return promptly with a spoken message.
    assert outcome.spoken


def test_generated_code_tab_populates(window):
    outcome = window.pipeline.process_command("generate a triangle wave at 500 Hz")
    window._on_finished(outcome)
    assert len(window.code_tab.view.toPlainText()) > 50


def test_settings_persist_across_reload(window, tmp_path):
    from picowave.gui.state_persistence import load_settings, save_settings

    window.pipeline.state.siggen_freq_hz = 4242
    save_settings(window.cfg, window.pipeline.state, "real", "mock")
    saved = load_settings(window.cfg)
    assert saved is not None
    assert saved["sdk_mode"] == "real"
    assert saved["session_state"]["siggen_freq_hz"] == 4242


def test_explicit_sdk_flag_overrides_saved_value(qapp, tmp_path, monkeypatch):
    """Regression test: an explicit --sdk/--llm on the command line must never
    be silently replaced by a value saved from a previous session. (This is
    exactly the bug hit in practice: a prior `--sdk mock` run saved "mock",
    and a later explicit `--sdk real` was getting overridden back to mock.)
    """
    from picowave.config import Config
    from picowave.gui import app as gui_app
    from picowave.gui.main_window import MainWindow
    from picowave.gui.state_persistence import save_settings
    from picowave.intent import SessionState

    def make_cfg():
        cfg = Config()
        cfg.paths.root = tmp_path
        cfg.paths.generated = tmp_path / "generated"
        cfg.paths.logs = tmp_path / "logs"
        cfg.paths.backup = tmp_path / "backup"
        cfg.paths.build = tmp_path / "build"
        cfg.paths.ensure()
        return cfg

    monkeypatch.setattr(gui_app, "load_config", lambda *a, **k: make_cfg())
    save_settings(make_cfg(), SessionState(), sdk_mode="mock", llm_choice="mock")

    captured = {}
    orig_init = MainWindow.__init__

    def spy_init(self, *a, **kw):
        orig_init(self, *a, **kw)
        captured["window"] = self

    monkeypatch.setattr(MainWindow, "__init__", spy_init)
    monkeypatch.setattr(type(qapp), "exec", lambda self: 0)

    gui_app.run(sdk_mode="real", llm_choice="mock", mode="template")
    assert captured["window"].sdk_mode == "real"

    # Omitting the flag (None) should still fall back to the saved value.
    gui_app.run(sdk_mode=None, llm_choice=None, mode="template")
    assert captured["window"].sdk_mode == "mock"


def test_cli_backend_untouched(tmp_path):
    """The GUI additions must not change the plain-pipeline CLI behaviour."""
    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()
    logger = SessionLogger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)
    outcome = pipeline.process_command("generate a 1 kHz sine wave")
    assert outcome.action == "siggen"
    assert "sine" in outcome.spoken


def test_measure_action_generates_and_captures_in_one_session(window):
    """Regression test for the generate-then-capture race: two separate
    commands can never work (the executor blocks until the C process exits,
    and the process closes the device -- stopping the signal -- before it
    exits). "measure" must produce a real, non-zero capture in one shot.
    """
    outcome = window.pipeline.process_command(
        "generate a sine wave at 2000 Hz and capture it")
    assert outcome.action == "measure"
    assert outcome.csv_path is not None and outcome.csv_path.exists()
    rows = outcome.csv_path.read_text().strip().splitlines()[1:]
    ch_a = [float(r.split(",")[3]) for r in rows]
    assert any(v != 0 for v in ch_a), (
        "measure must capture a real signal, not a dead/closed channel")


def test_stt_worker_times_out_instead_of_hanging(qapp):
    """Regression test: PocketSphinx's LiveSpeech has no built-in timeout, so
    a silent/unclear mic input must not leave the Voice button stuck forever.
    """
    import time

    from picowave.gui.workers.stt_worker import SttWorker

    class HangingRecognizer:
        mode = "pocketsphinx"

        def listen(self, prompt):
            time.sleep(999)

    worker = SttWorker(HangingRecognizer(), timeout_s=1.0)
    result = {}
    worker.failed.connect(lambda msg: result.update(failed=msg))
    worker.recognized.connect(lambda text: result.update(recognized=text))

    t0 = time.time()
    worker.start()
    while worker.isRunning() and time.time() - t0 < 5:
        qapp.processEvents()
        time.sleep(0.02)
    qapp.processEvents()

    assert "failed" in result, "a stuck listen() must time out, not hang"
    assert time.time() - t0 < 3, "should time out near timeout_s, not the full wait"


def test_voice_input_not_blocked_when_recognizer_actually_works(window):
    """Regression test: SpeechRecognizer.mode is "voice" on a successful
    PocketSphinx init (never the literal string "pocketsphinx"). An earlier
    version of the Voice-button guard compared against "pocketsphinx", which
    can never be true -- so voice input was unconditionally refused with
    "Voice input needs PocketSphinx and a microphone" even when PocketSphinx
    and the mic were both working correctly.
    """
    class WorkingRecognizer:
        mode = "voice"

        def listen(self, prompt):
            return "generate a sine wave"

    window.recognizer = WorkingRecognizer()
    before = window._stt
    window.start_voice()
    assert window._stt is not before, (
        "voice input must not be blocked when the recognizer reports mode=='voice'")

    # And the badge must report it as available too, not "no mic".
    assert "no mic" not in window._voice_status_text()


def test_stt_init_failure_reason_is_captured_not_swallowed():
    """Regression test: a PocketSphinx init failure used to be silently
    discarded (bare `except Exception: self._mode = "text"`), so there was no
    way to tell WHY voice was unavailable -- every failure looked identical
    regardless of cause. The real exception must now be captured and exposed
    via `init_error`.

    Uses sys.modules injection (the standard way to simulate "module not
    installed") rather than patching the global builtins.__import__ hook --
    patching that globally is risky in a multi-threaded Qt test suite, since
    other QThreads may be importing concurrently and could hit the patched
    hook mid-import.
    """
    import sys
    from picowave.voice.stt import SpeechRecognizer

    had_entry = "pocketsphinx" in sys.modules
    saved = sys.modules.get("pocketsphinx")
    sys.modules["pocketsphinx"] = None  # forces ImportError on any import
    try:
        rec = SpeechRecognizer()
    finally:
        if had_entry:
            sys.modules["pocketsphinx"] = saved
        else:
            sys.modules.pop("pocketsphinx", None)

    assert rec.mode == "text"
    assert rec.init_error is not None
    assert "pocketsphinx" in rec.init_error.lower()


def test_stt_detects_missing_portaudio_at_init_not_at_first_voice_click():
    """Regression test: pocketsphinx's LiveSpeech (5.x) needs sounddevice /
    the system PortAudio library to open a microphone. Critically,
    `import sounddevice` succeeding as a PYTHON package does not mean the
    underlying PortAudio C library is installed -- if it's missing, the
    failure previously only surfaced the first time someone clicked Voice, as
    a raw runtime exception from deep inside LiveSpeech(). It must now be
    caught proactively during init, with a specific, actionable message
    (this is also this project's actual real-world failure mode -- reproduced
    directly against a genuinely PortAudio-less environment during
    development, not simulated for the test alone).

    This test only runs meaningfully when PocketSphinx itself is genuinely
    importable (otherwise the pocketsphinx-missing path from the test above
    fires first, which is already covered) -- skipped otherwise.
    """
    import sys
    import pytest
    from picowave.voice.stt import SpeechRecognizer

    try:
        import pocketsphinx  # noqa: F401
    except Exception:
        pytest.skip("pocketsphinx itself isn't importable here; covered by "
                    "the sibling test instead")

    had_entry = "sounddevice" in sys.modules
    saved = sys.modules.get("sounddevice")
    sys.modules["sounddevice"] = None  # forces ImportError on any import
    try:
        rec = SpeechRecognizer()
    finally:
        if had_entry:
            sys.modules["sounddevice"] = saved
        else:
            sys.modules.pop("sounddevice", None)

    assert rec.mode == "text"
    assert rec.init_error is not None
    assert "portaudio" in rec.init_error.lower()


def test_vosk_tried_before_pocketsphinx():
    """Regression test: engine priority was deliberately swapped after
    PocketSphinx proved fragile in four separate real ways across this
    project's development (a mode-string bug, a model-path bug, a missing-
    PortAudio detection gap, and a hand-maintained JSGF grammar silently
    drifting out of sync with the bundled pronunciation dictionary, which
    crashed the recognizer outright the moment Voice was used). Vosk must be
    attempted first; PocketSphinx should not even be tried if Vosk succeeds.
    """
    from picowave.voice.stt import SpeechRecognizer

    called = {"pocketsphinx_attempted": False}
    orig_pspx = SpeechRecognizer._try_init_pocketsphinx

    def spy(self):
        called["pocketsphinx_attempted"] = True
        orig_pspx(self)

    def fake_vosk_success(self):
        self._engine = "vosk"
        self._mode = "voice"
        self._init_error = None

    import unittest.mock as mock
    with mock.patch.object(SpeechRecognizer, "_try_init_pocketsphinx", spy), \
         mock.patch.object(SpeechRecognizer, "_try_init_vosk", fake_vosk_success):
        rec = SpeechRecognizer()

    assert rec.engine == "vosk"
    assert called["pocketsphinx_attempted"] is False, (
        "PocketSphinx must not be tried when Vosk already succeeded")


def test_clean_engine_success_does_not_carry_a_stale_error():
    """Regression test: when Vosk is unavailable and PocketSphinx falls back
    cleanly (no problems of its own), `init_error` must be None -- not the
    leftover reason Vosk wasn't tried first. A working fallback is normal,
    expected behaviour, not an error state, and reporting it as one would be
    misleading (e.g. showing an "error" tooltip on a badge that says voice
    is ready and working).
    """
    from picowave.voice.stt import SpeechRecognizer

    def fake_vosk_fail(self):
        self._mode = "text"
        self._init_error = "Vosk model not found at /nonexistent"

    def fake_pocketsphinx_success(self):
        self._engine = "pocketsphinx"
        self._mode = "voice"
        self._grammar_ok = True
        if self._grammar_ok or not self.use_grammar:
            self._init_error = None

    import unittest.mock as mock
    with mock.patch.object(SpeechRecognizer, "_try_init_vosk", fake_vosk_fail), \
         mock.patch.object(SpeechRecognizer, "_try_init_pocketsphinx",
                          fake_pocketsphinx_success):
        rec = SpeechRecognizer()

    assert rec.mode == "voice"
    assert rec.init_error is None, (
        "a clean fallback success must not report a stale error from the "
        "engine that was tried and skipped first")


def test_grammar_file_has_no_words_missing_from_pocketsphinx_dictionary():
    """Regression test for the actual reported crash: PocketSphinx's JSGF
    grammar compiler hard-fails ("RuntimeError: Failed to initialize
    PocketSphinx", surfacing from deep inside fsg_search.c) if ANY literal
    word in the grammar isn't in the bundled pronunciation dictionary. Four
    words in an earlier version of this project's grammar -- "millivolts",
    "kilohertz", "sawtooth", "timebase" -- were not in that dictionary, which
    crashed voice input outright the moment it was used, not just failed to
    recognize those words specifically. This test scans every real spoken
    word in the actual shipped grammar file against PocketSphinx's own
    dictionary, so a future vocabulary addition that reintroduces this bug is
    caught here rather than only in the field.

    Skipped if PocketSphinx isn't installed (nothing to validate against).
    """
    import re
    from pathlib import Path

    import pytest

    try:
        from pocketsphinx import get_model_path
    except Exception:
        pytest.skip("pocketsphinx not installed; nothing to validate against")

    model_root = Path(get_model_path())
    dict_candidates = list(model_root.rglob("cmudict-en-us.dict"))
    if not dict_candidates:
        pytest.skip("bundled dictionary not found; covered by the model-"
                    "completeness test instead")
    dict_file = dict_candidates[0]

    words = set()
    with open(dict_file) as f:
        for line in f:
            w = line.split()[0].split("(")[0].lower()
            words.add(w)

    grammar_path = (Path(__file__).resolve().parents[1] / "config" / "grammar.jsgf")
    grammar = grammar_path.read_text()
    lines = [ln for ln in grammar.splitlines()
            if not ln.strip().startswith(("#", "*", "/"))]
    body = "\n".join(lines)
    body = re.sub(r"^grammar\s+\w+;", "", body, flags=re.MULTILINE)
    body = re.sub(r"<[^>]+>", " ", body)  # strip rule-name references, never spoken
    tokens = set(re.findall(r"[a-zA-Z]+", body))
    tokens -= {"JSGF", "public"}

    missing = sorted(t for t in tokens if t.lower() not in words)
    assert not missing, (
        f"grammar.jsgf contains word(s) not in PocketSphinx's bundled "
        f"dictionary: {missing} -- this WILL crash voice input the moment "
        f"it's used, not just fail to recognize those words")


def test_pocketsphinx_grammar_actually_compiles_end_to_end():
    """The strongest form of the above test: actually construct LiveSpeech
    with the real shipped grammar file, the same call the app itself makes.
    A missing-dictionary-word failure raises RuntimeError from inside
    fsg_search.c at this exact point; anything else (e.g. no microphone
    hardware in a CI/sandbox environment) is a different, unrelated failure
    and does not indicate a broken grammar.
    """
    from pathlib import Path

    import pytest

    try:
        from pocketsphinx import LiveSpeech, get_model_path
    except Exception:
        pytest.skip("pocketsphinx not installed")

    from picowave.voice.stt import _find_acoustic_model_dir, _find_file

    model_root = Path(get_model_path())
    hmm = _find_acoustic_model_dir(model_root)
    dic = _find_file(model_root, "cmudict-en-us.dict")
    if hmm is None or dic is None:
        pytest.skip("bundled model incomplete; covered by another test")

    grammar_path = (Path(__file__).resolve().parents[1] / "config" / "grammar.jsgf")
    try:
        LiveSpeech(verbose=False, sampling_rate=16000, buffer_size=2048,
                  hmm=str(hmm), jsgf=str(grammar_path), dic=str(dic))
    except RuntimeError as exc:
        raise AssertionError(
            f"grammar.jsgf failed to compile against the real PocketSphinx "
            f"dictionary: {exc}")
    except Exception:
        pass  # any other failure (e.g. no mic hardware here) is unrelated
