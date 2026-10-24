"""Voice workers: speech-to-text capture and text-to-speech playback.

Both wrap the existing backend (``SpeechRecognizer`` / ``Speaker``) on threads so
the GUI never blocks. They degrade gracefully: if PocketSphinx or espeak aren't
present the backend already falls back (text prompt / printing), and these
workers simply report that.

STT hardening: PocketSphinx's ``LiveSpeech`` has no built-in overall timeout --
if the mic never detects a clear utterance boundary (silence, background
noise, nothing said), the underlying call can block indefinitely. Without a
bound here, the GUI's mic button would show "Listening..." forever with no way
to cancel. ``SttWorker`` runs the actual recognition in an inner daemon thread
and gives up after ``timeout_s``, reporting a clear "no speech detected"
result instead of hanging. The inner thread is a daemon so it can't block
process exit even if PocketSphinx never returns.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal


class SttWorker(QThread):
    """Listen once and emit the recognised text (or an error/empty result).

    Bounded to ``timeout_s`` (default 15s) so an unclear or silent microphone
    input can never leave the mic button stuck.
    """

    recognized = Signal(str)
    failed = Signal(str)

    def __init__(self, recognizer, prompt: str = "Speak a command",
                 timeout_s: float = 15.0, parent=None) -> None:
        super().__init__(parent)
        self._recognizer = recognizer
        self._prompt = prompt
        self._timeout_s = timeout_s

    def run(self) -> None:
        result: dict = {}

        def _listen() -> None:
            try:
                result["text"] = self._recognizer.listen(self._prompt)
            except Exception as exc:  # noqa: BLE001
                result["error"] = f"{type(exc).__name__}: {exc}"

        # Daemon: if PocketSphinx never returns, this thread is abandoned
        # rather than hanging the worker (and therefore the mic button).
        inner = threading.Thread(target=_listen, daemon=True)
        inner.start()
        inner.join(timeout=self._timeout_s)

        if inner.is_alive():
            self.failed.emit(
                "No speech detected in time. Try again and speak clearly "
                "right after clicking Voice.")
            return
        if "error" in result:
            self.failed.emit(result["error"])
            return
        self.recognized.emit((result.get("text") or "").strip())


class TtsWorker(QThread):
    """Speak a line of text off the GUI thread."""

    done = Signal()

    def __init__(self, speaker, text: str, parent=None) -> None:
        super().__init__(parent)
        self._speaker = speaker
        self._text = text

    def run(self) -> None:
        try:
            self._speaker.say(self._text)
        except Exception:  # noqa: BLE001 - speech must never crash the app
            pass
        self.done.emit()
