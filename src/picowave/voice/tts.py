"""Text-to-speech via eSpeak NG (offline).

Shells out to the ``espeak-ng`` binary. If it is not installed, ``say`` prints
to the console instead, so feedback is never lost on a headless machine.
"""
from __future__ import annotations

import shutil
import subprocess


class Speaker:
    def __init__(self, voice: str = "en", speed_wpm: int = 165, enabled: bool = True):
        self.voice = voice
        self.speed_wpm = speed_wpm
        self.enabled = enabled
        self._bin = shutil.which("espeak-ng") or shutil.which("espeak")

    @property
    def available(self) -> bool:
        return self._bin is not None

    def say(self, text: str) -> None:
        if not text:
            return
        # Always mirror to console so there is a visible transcript.
        print(f"[speak] {text}")
        if not self.enabled or not self._bin:
            return
        try:
            subprocess.run(
                [self._bin, "-v", self.voice, "-s", str(self.speed_wpm), text],
                check=False, capture_output=True, timeout=30,
            )
        except Exception:
            pass  # TTS is best-effort; never break the pipeline on audio issues
