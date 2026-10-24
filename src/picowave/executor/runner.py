"""Run the compiled program and capture everything.

Captures stdout, stderr, exit code, and pulls out the ``RESULT:`` summary line
the templates print (used for spoken feedback). Runs inside ``generated/`` so any
CSV the program writes lands next to its source.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class ExecResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    result_line: Optional[str]   # the "RESULT: ..." summary, if present
    device_ok: bool              # False if exit code == 99 (device not opened)


class Executor:
    def __init__(self, workdir: Path, timeout_s: int = 60):
        self.workdir = workdir
        self.timeout_s = timeout_s

    def run(self, exe: Path) -> ExecResult:
        try:
            proc = subprocess.run([str(exe)], capture_output=True, text=True,
                                  cwd=str(self.workdir), timeout=self.timeout_s)
        except subprocess.TimeoutExpired:
            return ExecResult(False, 124, "", "execution timed out", None, True)
        except OSError as exc:
            return ExecResult(False, 126, "", f"could not execute: {exc}", None, True)

        result_line = None
        for line in proc.stdout.splitlines():
            if line.startswith("RESULT:"):
                result_line = line[len("RESULT:"):].strip()
                break

        device_ok = proc.returncode != 99  # 99 == "unable to open device"
        return ExecResult(
            ok=(proc.returncode == 0),
            returncode=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            result_line=result_line,
            device_ok=device_ok,
        )
