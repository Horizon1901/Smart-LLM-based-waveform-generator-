"""Speech-to-text: Vosk first, PocketSphinx as an optional fallback (offline).

Vosk is tried first. This project's real-hardware testing found PocketSphinx
fragile in four separate, distinct ways across development: a mode-string
comparison bug, a model-directory-layout mismatch, a missing-PortAudio
detection gap, and -- most seriously -- a hand-maintained JSGF grammar
silently drifting out of sync with PocketSphinx's bundled pronunciation
dictionary, which made the ENTIRE recognizer fail to even construct the
moment Voice was used (not a recognition-accuracy problem -- a hard crash).
Vosk does open-vocabulary recognition from its own trained model rather than
a hand-maintained grammar checked word-by-word against a fixed dictionary, so
it does not have that specific failure mode by construction. PocketSphinx
remains available as a secondary option (it can be more accurate once its
grammar is valid), and its own grammar is now validated for real at startup,
with automatic no-grammar fallback if that validation ever fails again.

If neither engine is available, the recognizer transparently falls back to
reading a typed line from stdin, so the rest of the pipeline is unchanged
either way -- voice is always optional, never required.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def _find_acoustic_model_dir(model_root: Path) -> Optional[Path]:
    """Find the acoustic model directory (the one containing 'mdef') under
    the pocketsphinx package's bundled model data.

    Deliberately NOT hardcoded to a specific nesting depth: different
    pocketsphinx package versions have shipped this at different depths
    (e.g. ``<model_root>/en-us`` in some, ``<model_root>/en-us/en-us`` in
    others), and hardcoding one gives a confusing, hard-to-diagnose failure
    ("does not contain acoustic model definition 'mdef'") on any version that
    doesn't match. Searching for the actual file is robust to that entirely.
    """
    if not model_root.exists():
        return None
    for hit in model_root.rglob("mdef"):
        return hit.parent
    return None


def _find_file(model_root: Path, filename: str) -> Optional[Path]:
    """Find a specific bundled model file by name, wherever it actually is."""
    if not model_root.exists():
        return None
    for hit in model_root.rglob(filename):
        return hit
    return None


class SpeechRecognizer:
    def __init__(self, grammar_file: Optional[Path] = None,
                 use_grammar: bool = True, mic_index: Optional[int] = None,
                 force_text: bool = False,
                 vosk_model_path: Optional[Path] = None):
        self.grammar_file = grammar_file
        self.use_grammar = use_grammar
        self.mic_index = mic_index
        self.force_text = force_text
        self.vosk_model_path = Path(vosk_model_path) if vosk_model_path else None
        self._engine: Optional[str] = None
        self._mode = "text"
        self._init_error: Optional[str] = None
        self._model_paths: Optional[tuple] = None
        self._grammar_ok = False  # whether the JSGF grammar itself validated
        self._vosk_model = None
        if not force_text:
            self._try_init_vosk()
            if self._mode != "voice":
                vosk_error = self._init_error
                self._try_init_pocketsphinx()
                if self._mode != "voice" and vosk_error:
                    # Neither engine worked -- report both reasons together,
                    # not just whichever was tried last, so the real cause of
                    # either one isn't silently lost.
                    self._init_error = (
                        f"Vosk: {vosk_error} | PocketSphinx: {self._init_error}")

    # -- Vosk (primary) --------------------------------------------------
    def _try_init_vosk(self) -> None:
        try:
            import vosk  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            self._mode = "text"
            self._init_error = f"{type(exc).__name__}: {exc}"
            return

        try:
            import sounddevice  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            self._mode = "text"
            self._init_error = (
                f"microphone audio backend unavailable ({type(exc).__name__}: "
                f"{exc}) -- try: sudo apt install libportaudio2")
            return

        model_path = self.vosk_model_path
        if model_path is None or not model_path.exists():
            self._mode = "text"
            self._init_error = (
                f"Vosk model not found at {model_path}. Download one -- see "
                f"VOICE_SETUP.md -- e.g.: curl -LO https://alphacephei.com/"
                f"vosk/models/vosk-model-small-en-us-0.15.zip && unzip "
                f"vosk-model-small-en-us-0.15.zip -d models/")
            return

        try:
            import vosk
            vosk.SetLogLevel(-1)  # suppress Kaldi's own noisy stderr logging
            self._vosk_model = vosk.Model(str(model_path))
        except Exception as exc:  # noqa: BLE001
            self._mode = "text"
            self._init_error = (
                f"could not load Vosk model at {model_path} "
                f"({type(exc).__name__}: {exc}) -- the download may be "
                f"incomplete or corrupted; re-download and re-extract it.")
            return

        self._engine = "vosk"
        self._mode = "voice"

    # -- PocketSphinx (fallback) ------------------------------------------
    def _try_init_pocketsphinx(self) -> None:
        try:
            from pocketsphinx import LiveSpeech, get_model_path  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            self._mode = "text"
            self._init_error = f"{type(exc).__name__}: {exc}"
            return

        # Import succeeding isn't enough -- validate the bundled model files
        # can actually be located too, and fail with a specific reason now
        # rather than a cryptic driver error the first time someone clicks
        # Voice. Resolved paths are cached for _listen_pocketsphinx to reuse.
        try:
            model_root = Path(get_model_path())
            hmm_dir = _find_acoustic_model_dir(model_root)
            lm_file = _find_file(model_root, "en-us.lm.bin")
            dict_file = _find_file(model_root, "cmudict-en-us.dict")
        except Exception as exc:  # noqa: BLE001
            self._mode = "text"
            self._init_error = f"could not resolve PocketSphinx model path: {exc}"
            return

        missing = [name for name, val in
                  (("acoustic model", hmm_dir), ("language model", lm_file),
                   ("dictionary", dict_file)) if val is None]
        if missing:
            self._mode = "text"
            self._init_error = (
                f"PocketSphinx's bundled model files are incomplete "
                f"(missing: {', '.join(missing)}) under {model_root}. "
                f"Try: pip install --force-reinstall pocketsphinx")
            return

        # The pocketsphinx package's LiveSpeech (as of 5.x) uses sounddevice
        # to open the microphone, not pyaudio -- an easy assumption to get
        # wrong if you're used to older tutorials. Critically, `sounddevice`
        # importing successfully as a PYTHON package does NOT mean the
        # underlying PortAudio C library is actually installed: `pip install
        # sounddevice` only installs the Python wrapper, and PortAudio itself
        # is a separate system package. If it's missing, `import sounddevice`
        # raises immediately -- but only the FIRST time it's imported, which
        # previously happened lazily inside LiveSpeech() the moment someone
        # clicked Voice, surfacing as a raw, easy-to-miss runtime exception
        # rather than a clear reason at startup. Check for it here instead.
        try:
            import sounddevice  # noqa: F401
        except Exception as exc:  # noqa: BLE001
            self._mode = "text"
            self._init_error = (
                f"microphone audio backend unavailable ({type(exc).__name__}: "
                f"{exc}). This is almost always a missing SYSTEM package, not "
                f"a Python one -- try: sudo apt install libportaudio2")
            return

        self._model_paths = (hmm_dir, lm_file, dict_file)

        # The grammar file is JSGF: a hand-maintained set of allowed phrases,
        # compiled against the acoustic model's fixed pronunciation
        # dictionary. If ANY word in it isn't in that dictionary, the grammar
        # fails to compile -- and this used to only be discovered the moment
        # Voice was actually clicked, surfacing as a raw crash
        # ("fsg_search.c ... is missing in the dictionary") deep inside
        # PocketSphinx. Validate it for real, right now, by actually
        # constructing a LiveSpeech instance with it (the same call
        # _listen_pocketsphinx will make) -- catching the failure here means
        # it's reported clearly at startup, and grammar-constrained
        # recognition is automatically disabled (falling back to open
        # dictation) rather than taking the whole engine down.
        if self.use_grammar and self.grammar_file and Path(self.grammar_file).exists():
            try:
                LiveSpeech(verbose=False, sampling_rate=16000, buffer_size=2048,
                          hmm=str(hmm_dir), jsgf=str(self.grammar_file),
                          dic=str(dict_file))
                self._grammar_ok = True
            except RuntimeError as exc:
                self._grammar_ok = False
                # Not fatal: PocketSphinx itself still works, just without
                # the grammar constraint (open dictation via the language
                # model instead). Note it so the cause isn't silently lost.
                self._init_error = (
                    f"(non-fatal) grammar '{self.grammar_file}' failed to "
                    f"compile -- {exc} -- falling back to open dictation")
            except Exception:  # noqa: BLE001
                # Anything else (e.g. no audio device in this environment) is
                # not a grammar problem -- the grammar is presumed fine.
                self._grammar_ok = True

        self._engine = "pocketsphinx"
        self._mode = "voice"
        if self._grammar_ok or not self.use_grammar:
            # A clean success -- discard any leftover failure note from a
            # prior engine attempt (e.g. Vosk being unavailable). That was
            # an expected part of normal fallback, not an actual problem
            # with the engine that ended up active, and should not be
            # surfaced as if something is still wrong.
            self._init_error = None

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def engine(self) -> Optional[str]:
        """Which engine is actually active: "vosk", "pocketsphinx", or None."""
        return self._engine

    @property
    def init_error(self) -> Optional[str]:
        """The real reason voice input is unavailable (or degraded), if so.

        None when an engine initialised fully and cleanly, or when running
        with force_text=True (no attempt was made). Previously failure
        reasons were silently discarded -- every failure looked identical
        regardless of cause. May be set even when `mode == "voice"` for a
        non-fatal degradation (e.g. the grammar didn't compile, so
        PocketSphinx fell back to open dictation).
        """
        return self._init_error

    def listen(self, prompt: str = "Speak a command") -> str:
        """Return one recognised (or typed) command string."""
        if self._mode == "voice" and self._engine == "vosk":
            return self._listen_vosk(prompt)
        if self._mode == "voice" and self._engine == "pocketsphinx":
            return self._listen_pocketsphinx(prompt)
        return self._listen_text(prompt)

    def _listen_pocketsphinx(self, prompt: str) -> str:
        from pocketsphinx import LiveSpeech
        # Resolved once, dynamically, in _try_init_pocketsphinx -- robust to
        # pocketsphinx package versions laying out their bundled model data
        # at different nesting depths.
        hmm_dir, lm_file, dict_file = self._model_paths
        kwargs = dict(
            verbose=False,
            sampling_rate=16000,
            buffer_size=2048,
            no_search=False,
            full_utt=False,
            hmm=str(hmm_dir),
            lm=str(lm_file),
            dic=str(dict_file),
        )
        use_grammar_now = (self.use_grammar and self._grammar_ok
                          and self.grammar_file and Path(self.grammar_file).exists())
        if use_grammar_now:
            kwargs.pop("lm", None)
            kwargs["jsgf"] = str(self.grammar_file)
        print(f"[voice:pocketsphinx{'+grammar' if use_grammar_now else ''}] {prompt} ...")
        try:
            engine = LiveSpeech(**kwargs)
        except RuntimeError:
            # Defense in depth: even though the grammar was validated at
            # startup, retry once without it rather than crashing -- covers
            # the grammar file being edited/replaced after init.
            if use_grammar_now:
                kwargs.pop("jsgf", None)
                kwargs["lm"] = str(lm_file)
                self._grammar_ok = False
                engine = LiveSpeech(**kwargs)
            else:
                raise
        for phrase in engine:
            text = str(phrase).strip()
            if text:
                return text
        return ""

    def _listen_vosk(self, prompt: str, max_seconds: float = 20.0) -> str:
        """Capture from the microphone via sounddevice and feed it to Vosk's
        streaming recognizer, returning as soon as one complete utterance is
        recognized (or the ``max_seconds`` safety bound is hit).
        """
        import queue
        import time

        import sounddevice as sd
        import vosk

        sample_rate = 16000
        recognizer = vosk.KaldiRecognizer(self._vosk_model, sample_rate)
        audio_q: "queue.Queue[bytes]" = queue.Queue()

        def _callback(indata, frames, time_info, status):  # noqa: ANN001
            audio_q.put(bytes(indata))

        print(f"[voice:vosk] {prompt} ...")
        deadline = time.monotonic() + max_seconds
        with sd.RawInputStream(samplerate=sample_rate, blocksize=8000,
                               device=self.mic_index, dtype="int16",
                               channels=1, callback=_callback):
            while time.monotonic() < deadline:
                try:
                    data = audio_q.get(timeout=0.5)
                except queue.Empty:
                    continue
                if recognizer.AcceptWaveform(data):
                    result = json.loads(recognizer.Result())
                    text = (result.get("text") or "").strip()
                    if text:
                        return text
                    # Empty result on an accepted waveform means silence was
                    # detected with nothing recognized -- keep listening
                    # rather than returning an empty command.
        # Safety-bound reached: return whatever the final partial guess was,
        # rather than nothing.
        final = json.loads(recognizer.FinalResult())
        return (final.get("text") or "").strip()

    def _listen_text(self, prompt: str) -> str:
        try:
            return input(f"[text] {prompt}: ").strip()
        except (EOFError, KeyboardInterrupt):
            return "exit"
