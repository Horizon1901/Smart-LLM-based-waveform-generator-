"""Automatic build step.

Compiles a generated C file with gcc, capturing stdout/stderr and the exit code.
Two link modes:
  * "mock" : -I mock, compile in mock/ps2000_mock.c, link libm  (offline dev)
  * "real" : -I <pico_include>, -L <pico_lib>, -lps2000            (real device)

The generated sources are identical in both modes; only include/link differ,
so a program proven to build against the mock also builds on the real target.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from ..config import CompilerConfig, Paths


@dataclass
class CompileResult:
    ok: bool
    exe_path: Optional[Path]
    command: str
    stdout: str
    stderr: str
    returncode: int


class Compiler:
    def __init__(self, cfg: CompilerConfig, paths: Paths):
        self.cfg = cfg
        self.paths = paths

    def _command(self, source: Path, exe: Path) -> List[str]:
        cmd = [self.cfg.cc, *self.cfg.cflags.split(), str(source), "-o", str(exe)]
        if self.cfg.sdk_mode == "mock":
            cmd += ["-I", str(self.paths.mock),
                    str(self.paths.mock / "ps2000_mock.c"), "-lm"]
        else:  # real PicoSDK
            cmd += ["-I", self.cfg.pico_include,
                    "-L", self.cfg.pico_lib, "-lps2000", "-lm"]
        return cmd

    def compile(self, source: Path) -> CompileResult:
        self.paths.build.mkdir(parents=True, exist_ok=True)
        exe = self.paths.build / (source.stem + (".exe" if _is_windows() else ""))
        cmd = self._command(source, exe)
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        except FileNotFoundError as exc:
            return CompileResult(False, None, " ".join(cmd), "",
                                 f"compiler not found: {exc}", 127)
        except subprocess.TimeoutExpired:
            return CompileResult(False, None, " ".join(cmd), "",
                                 "compilation timed out", 124)
        ok = proc.returncode == 0 and exe.exists()
        return CompileResult(ok, exe if ok else None, " ".join(cmd),
                             proc.stdout, proc.stderr, proc.returncode)


def _is_windows() -> bool:
    import platform
    return platform.system().lower().startswith("win")
