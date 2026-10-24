"""Tests for the "process" workflow: measurements, CSV discovery, gnuplot
export, and the pipeline's PROCESS action -- backend-level, no GUI needed.
"""
import csv
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picowave.measurements import (  # noqa: E402
    find_latest_csv, measure_csv, summarize,
)
from picowave.gnuplot_export import (  # noqa: E402
    PlotSpec, _build_script, gnuplot_available,
)


def _write_synthetic_csv(path: Path, freq_hz: float = 1000.0,
                         amplitude_mvpp: float = 2000.0, n: int = 2000,
                         window_s: float = 0.01, channel: str = "A") -> None:
    """Write a CSV of a known sine wave, so measurements can be checked
    against ground truth rather than just "did it run"."""
    t_s = np.linspace(0, window_s, n)
    y_mv = (amplitude_mvpp / 2.0) * np.sin(2 * np.pi * freq_hz * t_s)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sample", "time_ns", "chA_adc", "chA_mv", "chB_adc", "chB_mv"])
        for i in range(n):
            a = round(y_mv[i]) if channel == "A" else 0
            b = round(y_mv[i]) if channel == "B" else 0
            w.writerow([i, int(t_s[i] * 1e9), 0, a, 0, b])


def test_find_latest_csv_picks_highest_numbered_file():
    d = Path(tempfile.mkdtemp())
    (d / "acquisition_003.csv").write_text("x")
    (d / "acquisition_015.csv").write_text("x")
    (d / "acquisition_007.csv").write_text("x")
    latest = find_latest_csv(d)
    assert latest is not None and latest.name == "acquisition_015.csv"


def test_find_latest_csv_returns_none_when_empty():
    d = Path(tempfile.mkdtemp())
    assert find_latest_csv(d) is None


def test_measure_csv_matches_known_ground_truth():
    d = Path(tempfile.mkdtemp())
    path = d / "acquisition_001.csv"
    _write_synthetic_csv(path, freq_hz=1000.0, amplitude_mvpp=2000.0)

    results = measure_csv(path)
    assert len(results) == 1
    m = results[0]
    assert m.channel == "A"
    assert abs(m.freq_hz - 1000.0) < 20, f"frequency estimate off: {m.freq_hz}"
    assert abs(m.vpp_mv - 2000.0) < 50, f"Vpp estimate off: {m.vpp_mv}"
    assert abs(m.mean_mv) < 20, f"mean should be near zero for a sine: {m.mean_mv}"

    summary = summarize(results)
    assert "Channel A" in summary and "1000" in summary


def test_measure_csv_skips_flat_channel():
    """A channel written as all-zero (disabled/unconnected) should not be
    reported as if it were real data -- same convention as elsewhere."""
    d = Path(tempfile.mkdtemp())
    path = d / "acquisition_002.csv"
    _write_synthetic_csv(path, channel="A")  # only A has real data, B stays 0
    results = measure_csv(path)
    channels = {m.channel for m in results}
    assert channels == {"A"}


def test_classify_waveform_recognises_known_shapes_at_any_phase():
    """The three shapes this project generates must self-classify correctly
    regardless of phase offset -- the real signal's phase is never known in
    advance, so phase-invariance is a hard requirement, not a nice-to-have.
    """
    from picowave.measurements import classify_waveform

    def make(shape, freq=1000.0, n=2000, window_s=0.01, phase=0.0):
        t = np.linspace(0, window_s, n)
        p = 2 * np.pi * freq * t + phase
        if shape == "sine":
            y = np.sin(p)
        elif shape == "square":
            y = np.sign(np.sin(p))
        else:
            y = (2 / np.pi) * np.arcsin(np.sin(p))
        return t * 1e9, y * 1000

    for shape in ("sine", "square", "triangle"):
        for phase in (0.0, 1.3, 3.7):
            t_ns, mv = make(shape, phase=phase)
            label, conf = classify_waveform(t_ns, mv, 1000.0)
            assert label == shape, f"{shape} at phase {phase} misclassified as {label}"
            assert conf > 0.85


def test_classify_waveform_rejects_noise_as_none_of_the_above():
    from picowave.measurements import classify_waveform
    rng = np.random.default_rng(42)
    t_ns = np.linspace(0, 0.01, 2000) * 1e9
    mv = rng.normal(0, 1000, 2000)
    label, conf = classify_waveform(t_ns, mv, 1000.0)
    assert label is None, f"pure noise was classified as {label}"


def test_classify_waveform_robust_to_realistic_frequency_estimation_error():
    """Regression test for a real bug found during development: the
    classifier originally correlated against a single exact frequency, so
    even the ~4% error typical of the zero-crossing frequency estimator
    compounded into destructive phase drift over many cycles and caused a
    genuinely square signal to be reported as "none of the above". The
    classifier must search a small frequency neighborhood, not just phase, to
    be robust to realistic (imperfect) frequency estimates.
    """
    from picowave.measurements import classify_waveform

    n = 2000
    t_s = np.linspace(0, 0.008, n)
    true_freq = 1500.0
    y = np.sign(np.sin(2 * np.pi * true_freq * t_s)) * 1500
    # Feed a deliberately imperfect estimate (the exact ~4% error that broke
    # this originally), not the true frequency.
    imperfect_estimate = 1437.5
    label, conf = classify_waveform(t_s * 1e9, y, imperfect_estimate)
    assert label == "square", (
        f"should tolerate realistic frequency-estimation error, got {label}")
    assert conf > 0.85


def test_gnuplot_script_references_correct_columns():
    """The generated gnuplot script must reference the CSV's actual column
    layout (time_ns = col 2, chA_mv = col 4, chB_mv = col 6) and skip the
    header row -- these are easy to get subtly wrong and silently plot
    garbage instead of erroring.
    """
    script = _build_script([PlotSpec(csv_path=Path("/tmp/x.csv"), channels=["A", "B"])])
    assert "using 2:4" in script  # channel A
    assert "using 2:6" in script  # channel B
    assert "every ::1" in script  # skip header row
    assert "set datafile separator ','" in script


def test_gnuplot_script_is_valid_gnuplot_syntax():
    """Real end-to-end check: feed the actual generated script to the real
    gnuplot binary (headless dumb terminal, no display needed) against a real
    CSV, and confirm it runs to completion with no syntax/data errors.
    Skipped if gnuplot isn't installed in this environment.
    """
    import subprocess
    if not gnuplot_available():
        import pytest
        pytest.skip("gnuplot not installed in this environment")

    d = Path(tempfile.mkdtemp())
    csv_path = d / "acquisition_003.csv"
    _write_synthetic_csv(csv_path)

    script = _build_script([PlotSpec(csv_path=csv_path, channels=["A"])])
    headless = "set terminal dumb\n" + script.replace("pause mouse close\n", "")
    script_path = d / "check.gp"
    script_path.write_text(headless)

    result = subprocess.run(["gnuplot", str(script_path)],
                            capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, f"gnuplot error: {result.stderr}"
    assert len(result.stdout) > 50, "expected ASCII plot output"


def test_process_action_end_to_end_via_pipeline(monkeypatch, tmp_path):
    """The exact workflow requested: acquire, then a SEPARATE "process"
    command finds that capture, computes measurements, and (best-effort)
    triggers a plot -- without touching hardware or recompiling anything.
    """
    from picowave.config import Config
    from picowave.llm.client import MockLLM
    from picowave.logger import get_logger
    from picowave.pipeline import Pipeline

    # Don't spawn a real gnuplot window during the test suite -- just verify
    # the pipeline calls it with sensible arguments.
    calls = {}
    import picowave.pipeline as pipeline_mod

    def fake_launch(specs, x_col=None, y_col=None, style="lines"):
        calls["specs"] = specs
        return None  # simulate success

    monkeypatch.setattr(pipeline_mod, "launch_gnuplot_multi", fake_launch)

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()

    logger = get_logger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)

    out1 = pipeline.process_command("acquire 1024 samples from channel A")
    assert out1.csv_path is not None and out1.csv_path.exists()

    out2 = pipeline.process_command("process")
    assert out2.action == "process"
    assert out2.csv_path == out1.csv_path, "process must find the just-made capture"
    assert calls["specs"][0].csv_path == out1.csv_path, "gnuplot should be called with that CSV"
    assert "A" in calls["specs"][0].channels
    assert out2.spoken and "Channel" in out2.spoken  # a real measurement summary


def test_process_with_no_prior_capture_is_clean_not_a_crash(tmp_path):
    from picowave.config import Config
    from picowave.llm.client import MockLLM
    from picowave.logger import get_logger
    from picowave.pipeline import Pipeline

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()

    logger = get_logger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)

    out = pipeline.process_command("process")
    assert out.csv_path is None
    assert "acquire" in out.spoken.lower()


def test_mockllm_parses_multi_file_process_with_titles():
    """The exact real-world example this feature was built for:
    "process file 1 and file 2 and add title as square and triangle" must
    resolve to process_files=[1,2] and process_titles=["square","triangle"].
    """
    from picowave.llm.client import MockLLM
    from picowave.llm.prompts import INTENT_SYSTEM_PROMPT, build_intent_prompt
    from picowave.intent import Intent, SessionState

    llm = MockLLM()
    state = SessionState()
    raw = llm.generate(INTENT_SYSTEM_PROMPT, build_intent_prompt(
        "process file 1 and file 2 and add title as square and triangle", state))
    intent = Intent.from_json(raw, raw_text="process file 1 and file 2")

    assert intent.action.value == "process"
    assert intent.params.get("process_files") == [1, 2]
    assert intent.params.get("process_titles") == ["square", "triangle"]


def test_mockllm_parses_verbal_gnuplot_column_and_style():
    """"use column 1 and 3 with lp" should map onto real gnuplot syntax
    (using 1:3, with linespoints) rather than requiring the person to write
    gnuplot syntax by hand.
    """
    from picowave.llm.client import MockLLM
    from picowave.llm.prompts import INTENT_SYSTEM_PROMPT, build_intent_prompt
    from picowave.intent import Intent, SessionState

    llm = MockLLM()
    state = SessionState()
    raw = llm.generate(INTENT_SYSTEM_PROMPT, build_intent_prompt(
        "process using column 1 and 3 with lp", state))
    intent = Intent.from_json(raw, raw_text="process using column 1 and 3 with lp")

    assert intent.params.get("plot_x_col") == 1
    assert intent.params.get("plot_y_col") == 3
    assert intent.params.get("plot_style") == "lp"


def test_process_multi_file_end_to_end_with_correct_file_resolution(monkeypatch, tmp_path):
    """Full pipeline test: two real captures, the exact user command, and
    verification that "file 1" resolves to the NEWEST capture (not literal
    filesystem numbering) with titles matched positionally and correctly
    attributed to the right file.
    """
    import csv as csv_mod
    import numpy as np
    from picowave.config import Config
    from picowave.llm.client import MockLLM
    from picowave.logger import get_logger
    from picowave.pipeline import Pipeline
    import picowave.pipeline as pipeline_mod

    calls = {}
    monkeypatch.setattr(pipeline_mod, "launch_gnuplot_multi",
                        lambda specs, x_col=None, y_col=None, style="lines":
                        calls.update(specs=specs, x_col=x_col, y_col=y_col, style=style))

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()
    gen_dir = cfg.paths.generated

    def write(name, shape):
        n = 800
        t = np.linspace(0, 0.004, n)
        ph = 2 * np.pi * 1000 * t
        y = (np.sign(np.sin(ph)) if shape == "square"
            else (2 / np.pi) * np.arcsin(np.sin(ph)))
        with open(gen_dir / name, "w", newline="") as f:
            w = csv_mod.writer(f)
            w.writerow(["sample", "time_ns", "chA_adc", "chA_mv", "chB_adc", "chB_mv"])
            for i in range(n):
                w.writerow([i, int(t[i] * 1e9), 0, round(y[i] * 1000), 0, 0])

    write("acquisition_001.csv", "triangle")  # older -> "file 2"
    write("acquisition_002.csv", "square")    # newer -> "file 1"

    logger = get_logger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)
    out = pipeline.process_command(
        "process file 1 and file 2 and add title as square and triangle")

    assert out.action == "process"
    assert "square" in out.spoken and "triangle" in out.spoken
    assert out.csv_path.name == "acquisition_002.csv", "file 1 must be the newest capture"

    plotted_names = [s.csv_path.name for s in calls["specs"]]
    plotted_titles = [s.title for s in calls["specs"]]
    assert plotted_names == ["acquisition_002.csv", "acquisition_001.csv"]
    assert plotted_titles == ["square", "triangle"]


def test_process_backward_compatible_single_file_unchanged(tmp_path):
    """Plain "process" (no file/title/column params) must behave exactly as
    before this feature was added: just the newest capture, single summary.
    """
    import csv as csv_mod
    import numpy as np
    from picowave.config import Config
    from picowave.llm.client import MockLLM
    from picowave.logger import get_logger
    from picowave.pipeline import Pipeline

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()
    gen_dir = cfg.paths.generated

    n = 500
    t = np.linspace(0, 0.003, n)
    y = np.sin(2 * np.pi * 1000 * t) * 1000
    with open(gen_dir / "acquisition_001.csv", "w", newline="") as f:
        w = csv_mod.writer(f)
        w.writerow(["sample", "time_ns", "chA_adc", "chA_mv", "chB_adc", "chB_mv"])
        for i in range(n):
            w.writerow([i, int(t[i] * 1e9), 0, round(y[i]), 0, 0])

    logger = get_logger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)
    out = pipeline.process_command("process")

    assert out.csv_path.name == "acquisition_001.csv"
    assert "|" not in out.spoken  # single-file summary has no multi-file separator


def _write_shape_csv(path, shape="square", freq=1000.0, chan="A", n=800):
    import csv as csv_mod
    import numpy as np
    t = np.linspace(0, 0.004, n)
    ph = 2 * np.pi * freq * t
    y = (np.sign(np.sin(ph)) if shape == "square"
        else (2 / np.pi) * np.arcsin(np.sin(ph)))
    with open(path, "w", newline="") as f:
        w = csv_mod.writer(f)
        w.writerow(["sample", "time_ns", "chA_adc", "chA_mv", "chB_adc", "chB_mv"])
        for i in range(n):
            a = round(y[i] * 1000) if chan == "A" else 0
            b = round(y[i] * 1000) if chan == "B" else 0
            w.writerow([i, int(t[i] * 1e9), 0, a, 0, b])


def test_process_summary_always_states_real_filename_even_with_a_title(tmp_path):
    """Regression test for the exact confusion a real user hit: "process file
    4" resolved (correctly, per ordinal semantics) to an OLDER capture than
    expected, but the response gave no way to notice this because a given
    title fully replaced the real filename in the output. The real, stable
    filename must now ALWAYS be visible -- title or not -- specifically so an
    ordinal reference landing on an unexpected file is immediately obvious.
    """
    from picowave.config import Config
    from picowave.llm.client import MockLLM
    from picowave.logger import get_logger
    from picowave.pipeline import Pipeline

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()
    gen_dir = cfg.paths.generated

    # Four captures, oldest to newest -- "file 4" (ordinal) should resolve to
    # the OLDEST of these, exactly the scenario that caused the confusion.
    for i in range(1, 5):
        _write_shape_csv(gen_dir / f"acquisition_{i:03d}.csv", chan="A")

    logger = get_logger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)
    out = pipeline.process_command("process file 4, title it mylabel")

    assert out.csv_path.name == "acquisition_001.csv", (
        "file 4 (ordinal, 4th most recent) must resolve to the OLDEST of "
        "four captures")
    assert "mylabel" in out.spoken, "the given title must still appear"
    assert "acquisition_001" in out.spoken, (
        "the REAL filename must be visible even when a title is given -- "
        "this is the actual fix; previously the title fully replaced it")


def test_process_single_title_now_parses_not_just_two_or_more():
    """A single title ("title it X") is very natural phrasing for a
    single-file process command and must parse -- previously the title regex
    required at least two titles joined by "and"/",", so a bare single title
    was silently dropped entirely.
    """
    from picowave.llm.client import MockLLM
    from picowave.llm.prompts import INTENT_SYSTEM_PROMPT, build_intent_prompt
    from picowave.intent import Intent, SessionState

    llm = MockLLM()
    state = SessionState()
    raw = llm.generate(INTENT_SYSTEM_PROMPT, build_intent_prompt(
        "process file 4, title it mylabel", state))
    intent = Intent.from_json(raw, raw_text="x")
    assert intent.params.get("process_titles") == ["mylabel"]


def test_process_literal_capture_id_is_stable_unlike_ordinal(tmp_path):
    """"process acquisition N" (literal ID) must always resolve to the same
    file regardless of what else has been captured since -- unlike "file N"
    (ordinal), which is deliberately relative and shifts. This is the
    alternative addressing mode added alongside the filename-visibility fix,
    for when the person already knows the specific capture they want.
    """
    from picowave.config import Config
    from picowave.llm.client import MockLLM
    from picowave.logger import get_logger
    from picowave.pipeline import Pipeline

    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.generated = tmp_path / "generated"
    cfg.paths.logs = tmp_path / "logs"
    cfg.paths.backup = tmp_path / "backup"
    cfg.paths.build = tmp_path / "build"
    cfg.paths.ensure()
    gen_dir = cfg.paths.generated

    for i in range(1, 4):
        _write_shape_csv(gen_dir / f"acquisition_{i:03d}.csv", chan="A")

    logger = get_logger(cfg.paths.logs)
    pipeline = Pipeline(cfg, MockLLM(), logger)

    out1 = pipeline.process_command("process acquisition 2")
    assert out1.csv_path.name == "acquisition_002.csv"

    # Make a new capture -- an ordinal "file 1" would now point somewhere
    # else, but the literal reference must still resolve identically.
    _write_shape_csv(gen_dir / "acquisition_004.csv", chan="A")
    out2 = pipeline.process_command("process acquisition 2")
    assert out2.csv_path.name == "acquisition_002.csv", (
        "a literal capture-ID reference must stay stable across new captures")
