"""Tests that generation produces distinct, compilable files.

Runnable with pytest, or directly:  python tests/test_codegen.py
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from picowave.codegen import CodeGenerator  # noqa: E402
from picowave.compiler import Compiler  # noqa: E402
from picowave.config import Config  # noqa: E402
from picowave.intent import Action, Intent, SessionState  # noqa: E402


def _gen_dir():
    d = Path(tempfile.mkdtemp(prefix="pw_gen_"))
    return d


def test_ids_are_monotonic_and_never_overwrite():
    gen = CodeGenerator(ROOT / "templates", _gen_dir())
    state = SessionState()
    p1 = gen.generate(Intent(Action.ACQUIRE, {"channel": "A"}, "acquire A"), state)
    p2 = gen.generate(Intent(Action.ACQUIRE, {"channel": "B"}, "acquire B"), state)
    assert p1.gen_id == "001" and p2.gen_id == "002"
    assert p1.path.exists() and p2.path.exists()
    assert p1.path.read_text() != p2.path.read_text()


def test_all_actions_compile_against_mock():
    gdir = _gen_dir()
    gen = CodeGenerator(ROOT / "templates", gdir)
    cfg = Config()
    cfg.compiler.sdk_mode = "mock"
    cfg.paths.build = Path(tempfile.mkdtemp(prefix="pw_build_"))
    comp = Compiler(cfg.compiler, cfg.paths)
    state = SessionState()

    cases = [
        Intent(Action.ACQUIRE, {"channel": "A"}, "acquire A"),
        Intent(Action.ACQUIRE, {"channel": "B", "trigger_enabled": True,
                                "trigger_level_mv": 500}, "acquire B triggered"),
        Intent(Action.SIGGEN, {"siggen_wave": "square", "siggen_freq_hz": 2000}, "square"),
        Intent(Action.ARB, {"arb_shape": "triangle"}, "arb triangle"),
    ]
    for it in cases:
        st = SessionState(**state.__dict__)
        st.apply(it.params)
        res = gen.generate(it, st)
        cr = comp.compile(res.path)
        assert cr.ok, f"compile failed for {it.action}: {cr.stderr}"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\n{len(fns)} tests passed")
