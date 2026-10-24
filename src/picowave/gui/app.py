"""Application bootstrap: wire the existing backend to the GUI and run it."""
from __future__ import annotations

import sys
from typing import Optional

from ..config import Config, load_config
from ..llm.client import MockLLM, OllamaClient
from ..logger import get_logger
from ..pipeline import Pipeline
from ..voice import SpeechRecognizer, Speaker


def _make_llm(cfg: Config, choice: str):
    """Mirror the CLI's --llm selection (auto | ollama | mock)."""
    if choice == "mock":
        return MockLLM()
    client = OllamaClient(cfg.llm.host, cfg.llm.model, cfg.llm.request_timeout_s)
    if choice == "ollama":
        return client
    # auto: use Ollama if reachable, else fall back to the rule-based mock.
    return client if client.available() else MockLLM()


def run(sdk_mode: Optional[str] = None, llm_choice: Optional[str] = None,
        mode: str = "template", argv: Optional[list] = None) -> int:
    """Launch the desktop GUI. Returns the Qt exit code.

    ``sdk_mode``/``llm_choice`` of ``None`` mean "not explicitly requested" --
    the last-saved choice is used if one exists, otherwise "mock"/"auto". An
    explicit value always wins over anything saved, so a real ``--sdk real``
    on the command line can never be silently overridden by a previous mock
    session's saved settings.
    """
    from PySide6.QtWidgets import QApplication

    from .main_window import MainWindow
    from .state_persistence import apply_session_state, load_settings
    from .theme import apply_theme

    # load_config() overlays config/config.yaml (model choice, timeouts, etc.)
    # exactly like the CLI does -- previously the GUI silently ignored it.
    cfg = load_config()

    saved = load_settings(cfg)
    if sdk_mode is None:
        sdk_mode = (saved or {}).get("sdk_mode") or "mock"
    if llm_choice is None:
        llm_choice = (saved or {}).get("llm_choice") or "auto"

    cfg.compiler.sdk_mode = sdk_mode  # "mock" | "real"
    logger = get_logger(cfg.paths.logs)
    llm = _make_llm(cfg, llm_choice)
    pipeline = Pipeline(cfg, llm, logger, mode=mode)
    if saved and isinstance(saved.get("session_state"), dict):
        apply_session_state(pipeline.state, saved["session_state"])

    # Voice backends (degrade gracefully if PocketSphinx / espeak are absent).
    speaker = Speaker(cfg.voice.espeak_voice, cfg.voice.espeak_speed_wpm,
                      enabled=cfg.voice.tts_enabled)
    grammar = cfg.paths.root / cfg.voice.grammar_file
    vosk_model = cfg.paths.root / cfg.voice.vosk_model_path
    recognizer = SpeechRecognizer(
        grammar_file=grammar, use_grammar=cfg.voice.stt_use_grammar,
        mic_index=cfg.voice.mic_device_index, force_text=False,
        vosk_model_path=vosk_model)

    app = QApplication.instance() or QApplication(argv or sys.argv)
    apply_theme(app)
    window = MainWindow(pipeline, logger, llm, sdk_mode, cfg,
                        recognizer, speaker, llm_choice)
    window.show()
    return app.exec()
