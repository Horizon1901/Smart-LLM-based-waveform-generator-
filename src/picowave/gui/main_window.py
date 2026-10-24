"""Main application window.

Layout:
    +-----------------------------------------------------+
    | title bar:  LLM Project            [status badges]  |
    +----------+------------------------------------------+
    | command  |  tabs: Result | Generated C | CSV viewer |
    | panel    |                                          |
    +----------+------------------------------------------+
    | console                                             |
    +-----------------------------------------------------+
Commands run on a worker thread; results are routed to the tabs. Voice input,
spoken results, a settings dialog, and background status polling are wired here.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QMainWindow, QSplitter, QTabWidget, QVBoxLayout,
    QWidget,
)

from ..pipeline import CommandOutcome, Pipeline
from .app import _make_llm
from .dialogs import SettingsDialog
from .log_bridge import LogBridge, install_console_bridge
from .panels import CommandPanel, ConsolePanel
from .state_persistence import save_settings
from .tabs import CodeTab, CsvTab, ResultTab
from .theme import ERR, OK, TEXT_MUTED, WARN
from .workers import CommandWorker, StatusWorker, SttWorker, TtsWorker

_STATUS_POLL_MS = 8000


class MainWindow(QMainWindow):
    def __init__(self, pipeline: Pipeline, logger, llm, sdk_mode: str,
                 cfg, recognizer, speaker, llm_choice: str = "auto") -> None:
        super().__init__()
        self.pipeline = pipeline
        self.logger = logger
        self.llm = llm
        self.sdk_mode = sdk_mode
        self.cfg = cfg
        self.recognizer = recognizer
        self.speaker = speaker
        self.llm_choice = llm_choice

        self._worker: Optional[CommandWorker] = None
        self._stt: Optional[SttWorker] = None
        self._tts: Optional[TtsWorker] = None
        self._status: Optional[StatusWorker] = None
        # Tracks what kind of view the Result tab is currently showing
        # ("siggen" ideal-waveform | "csv" real capture | None). Used so a
        # settings-only command can quietly refresh a live ideal-waveform view.
        self._result_view: Optional[str] = None

        self.setWindowTitle("LLM Project")
        self.resize(1120, 720)
        self._build_menu()
        self._build_ui()

        self.bridge = LogBridge()
        self.bridge.message.connect(self.console.append)
        install_console_bridge(self.bridge, logger)

        # Background status polling (Ollama availability can block, so off-thread).
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._poll_status)
        self._status_timer.start(_STATUS_POLL_MS)
        self._poll_status()

        self.logger.info("GUI ready")

    # -- construction ------------------------------------------------------
    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Menu")
        settings_action = QAction("Settings...", self)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _build_ui(self) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(8)

        outer.addLayout(self._build_titlebar())

        mid = QSplitter(Qt.Horizontal)
        self.command = CommandPanel()
        self.command.command_submitted.connect(self.run_command)
        self.command.voice_requested.connect(self.start_voice)
        mid.addWidget(self.command)

        self.tabs = QTabWidget()
        self.result_tab = ResultTab()
        self.code_tab = CodeTab()
        self.csv_tab = CsvTab()
        self.tabs.addTab(self.result_tab, "Result")
        self.tabs.addTab(self.code_tab, "Generated C")
        self.tabs.addTab(self.csv_tab, "CSV viewer")
        mid.addWidget(self.tabs)
        mid.setStretchFactor(1, 1)
        outer.addWidget(mid, 1)

        self.console = ConsolePanel()
        outer.addWidget(self.console)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Ready")

    def _build_titlebar(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        title = QLabel("LLM Project")
        title.setStyleSheet("font-size:15px; font-weight:500;")
        bar.addWidget(title)
        bar.addStretch(1)
        self.badge_llm = QLabel()
        self.badge_sdk = QLabel()
        self.badge_dev = QLabel()
        self.badge_voice = QLabel()
        for b in (self.badge_llm, self.badge_sdk, self.badge_dev, self.badge_voice):
            b.setStyleSheet("padding:2px 8px;")
            bar.addWidget(b)
        return bar

    def _badge(self, label: QLabel, text: str, color: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"padding:2px 8px; color:{color};")

    # -- status polling ----------------------------------------------------
    def _poll_status(self) -> None:
        if self._status is not None and self._status.isRunning():
            return
        self._status = StatusWorker(self.llm)
        self._status.status.connect(self._apply_status)
        self._status.start()

    def _apply_status(self, is_mock: bool, ollama_ok: bool) -> None:
        if is_mock:
            self._badge(self.badge_llm, "LLM: mock", WARN)
        else:
            self._badge(self.badge_llm, "Ollama ready" if ollama_ok
                        else "Ollama down", OK if ollama_ok else ERR)
        self._badge(self.badge_sdk, f"SDK: {self.sdk_mode}",
                    WARN if self.sdk_mode == "mock" else OK)
        self._badge(self.badge_dev, "device: opened per command",
                    TEXT_MUTED)
        self._badge(self.badge_voice, self._voice_status_text(),
                    self._voice_status_color())
        init_error = getattr(self.recognizer, "init_error", None)
        self.badge_voice.setToolTip(init_error or "")

    def _voice_status_text(self) -> str:
        # SpeechRecognizer.mode is "voice" on a successful PocketSphinx init
        # and "text" otherwise -- it is NEVER the string "pocketsphinx". An
        # earlier version of this check compared against "pocketsphinx",
        # which can never be true, so the mic was reported/blocked as
        # unavailable unconditionally regardless of whether it actually
        # worked. Keep this comparing against "voice".
        stt_ok = getattr(self.recognizer, "mode", "text") == "voice"
        tts_ok = getattr(self.speaker, "available", False) and self.speaker.enabled
        engine = getattr(self.recognizer, "engine", None)
        engine_label = f" ({engine})" if engine else ""
        if stt_ok and tts_ok:
            return f"voice: mic{engine_label} + speech ready"
        if stt_ok:
            return f"voice: mic{engine_label} ready, no speech engine"
        if tts_ok:
            return "voice: speech ready, no mic"
        return "voice: text only (no mic/PocketSphinx, no espeak)"

    def _voice_status_color(self) -> str:
        stt_ok = getattr(self.recognizer, "mode", "text") == "voice"
        tts_ok = getattr(self.speaker, "available", False) and self.speaker.enabled
        if stt_ok and tts_ok:
            return OK
        if stt_ok or tts_ok:
            return WARN
        return TEXT_MUTED

    # -- settings persistence ----------------------------------------------
    # Restoring the last-used SDK/LLM choice and session state now happens
    # once, in app.run(), BEFORE this window is constructed -- so an explicit
    # --sdk/--llm on the command line always wins over a saved value. Doing it
    # here too would silently re-override an explicit CLI flag with a stale
    # saved one, which is the bug this comment replaces.
    def _save_settings(self) -> None:
        save_settings(self.cfg, self.pipeline.state, self.sdk_mode, self.llm_choice)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._save_settings()
        super().closeEvent(event)

    # -- settings ----------------------------------------------------------
    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.sdk_mode, self.llm_choice, self)
        if not dlg.exec():
            return
        sdk_mode, llm_choice = dlg.values()
        self.sdk_mode = sdk_mode
        self.cfg.compiler.sdk_mode = sdk_mode
        if llm_choice != self.llm_choice:
            self.llm_choice = llm_choice
            self.llm = _make_llm(self.cfg, llm_choice)
            self.pipeline.llm = self.llm
            self.logger.info(f"LLM backend switched to {llm_choice}")
        self.logger.info(f"SDK mode set to {sdk_mode}")
        self._poll_status()
        self._save_settings()

    # -- voice input -------------------------------------------------------
    def start_voice(self) -> None:
        if self._stt is not None and self._stt.isRunning():
            return
        if getattr(self.recognizer, "mode", "text") != "voice":
            reason = getattr(self.recognizer, "init_error", None)
            if reason:
                self.command.add_assistant(
                    f"Voice input is unavailable: {reason}. "
                    "Type the command instead.")
            else:
                self.command.add_assistant(
                    "Voice input needs PocketSphinx and a microphone. "
                    "Type the command instead.")
            return
        self.command.set_listening(True)
        self.statusBar().showMessage("Listening...")
        self._stt = SttWorker(self.recognizer)
        self._stt.recognized.connect(self._on_recognized)
        self._stt.failed.connect(self._on_voice_failed)
        self._stt.start()

    def _on_recognized(self, text: str) -> None:
        self.command.set_listening(False)
        if text:
            self.run_command(text)
        else:
            self.command.add_assistant("I did not catch that.")
            self.statusBar().showMessage("Ready")

    def _on_voice_failed(self, message: str) -> None:
        self.command.set_listening(False)
        self.command.add_assistant(f"Voice input unavailable: {message}")
        self.logger.warn(message)
        self.statusBar().showMessage("Ready")

    # -- command execution -------------------------------------------------
    def run_command(self, text: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        self.command.add_user(text)
        self.command.set_busy(True)
        self.statusBar().showMessage(f"Running: {text}")

        self._worker = CommandWorker(self.pipeline, text)
        self._worker.finished_cmd.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _on_finished(self, outcome: CommandOutcome) -> None:
        self.command.set_busy(False)
        self.command.add_assistant(outcome.spoken or "(no response)")
        self.statusBar().showMessage(outcome.spoken or "Done")

        if self.command.speak_enabled() and outcome.spoken:
            self._speak(outcome.spoken)

        if outcome.should_exit:
            self.close()
            return

        if outcome.generated_file:
            self.code_tab.show_file(outcome.generated_file)

        action = outcome.action
        if action == "siggen":
            s = self.pipeline.state
            self.result_tab.show_siggen(s.siggen_wave, s.siggen_freq_hz,
                                        s.amplitude_mvpp, s.offset_mv)
            self._result_view = "siggen"
            self.tabs.setCurrentWidget(self.result_tab)
        elif action in ("acquire", "measure", "process") and outcome.csv_path:
            self.result_tab.show_csv(outcome.csv_path)
            self.csv_tab.show_csv(outcome.csv_path)
            self._result_view = "csv"
            self.tabs.setCurrentWidget(self.result_tab)
        elif action == "arb":
            s = self.pipeline.state
            self.result_tab.show_siggen(s.arb_shape, s.siggen_freq_hz,
                                        s.amplitude_mvpp, s.offset_mv)
            self._result_view = "siggen"
            self.tabs.setCurrentWidget(self.result_tab)
        elif action == "set_param" and self._result_view == "siggen":
            # This is the fix for "I changed a setting but the plot didn't
            # change": a settings-only command (absolute -- "set frequency to
            # X" -- or relative -- "increase the amplitude") never re-rendered
            # the Result tab before, so the on-screen waveform silently went
            # stale the moment you adjusted anything. If the Result tab is
            # currently showing an ideal waveform, redraw it with the updated
            # values immediately -- no need to re-run "generate" just to see
            # a parameter change reflected. Deliberately does NOT switch tabs,
            # so it's a quiet live-update rather than yanking focus.
            s = self.pipeline.state
            self.result_tab.show_siggen(s.siggen_wave, s.siggen_freq_hz,
                                        s.amplitude_mvpp, s.offset_mv)

    def _on_failed(self, message: str) -> None:
        self.command.set_busy(False)
        self.command.add_assistant(f"Error: {message}")
        self.logger.error(message)
        self.statusBar().showMessage("Command failed")

    # -- text to speech ----------------------------------------------------
    def _speak(self, text: str) -> None:
        if self._tts is not None and self._tts.isRunning():
            return
        self._tts = TtsWorker(self.speaker, text)
        self._tts.start()
