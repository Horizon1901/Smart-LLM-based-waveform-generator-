"""LLM Project -- command-line entry point.

Modes:
  interactive (default) : voice loop (or typed loop if no mic) until "exit"
  --once "text"         : run a single command and exit
  --batch FILE          : run each line of FILE as a command

Examples:
  python -m picowave.main --text --once "generate a 1 kHz sine wave"
  python -m picowave.main --batch tests/sample_commands.txt --sdk mock
  python -m picowave.main                       # full voice mode
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .llm import MockLLM, OllamaClient
from .logger import get_logger
from .pipeline import Pipeline
from .voice import SpeechRecognizer, Speaker


def _select_llm(cfg, which: str, logger):
    if which == "mock":
        logger.info("LLM: using rule-based MockLLM")
        return MockLLM()
    client = OllamaClient(cfg.llm.host, cfg.llm.model, cfg.llm.request_timeout_s)
    if which == "ollama":
        if not client.available():
            logger.warn("Ollama not reachable; falling back to MockLLM")
            return MockLLM()
        logger.info(f"LLM: Ollama model {cfg.llm.model}")
        return client
    # auto
    if client.available():
        logger.info(f"LLM: Ollama model {cfg.llm.model}")
        return client
    logger.info("LLM: Ollama unavailable, using MockLLM")
    return MockLLM()


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="picowave", description=__doc__)
    p.add_argument("--config", default=None, help="path to config.yaml")
    p.add_argument("--mode", choices=["template", "llm-freeform"], default="template",
                   help="C generation strategy (default: template)")
    p.add_argument("--sdk", choices=["mock", "real"], default=None,
                   help="link the offline mock SDK or the installed PicoSDK")
    p.add_argument("--llm", choices=["auto", "ollama", "mock"], default="auto")
    p.add_argument("--text", action="store_true", help="type commands (no microphone)")
    p.add_argument("--no-tts", action="store_true", help="disable spoken output")
    p.add_argument("--once", metavar="TEXT", help="run one command then exit")
    p.add_argument("--batch", metavar="FILE", help="run each line of FILE as a command")
    return p


def main(argv=None) -> int:
    args = build_argparser().parse_args(argv)
    cfg = load_config(args.config)
    if args.sdk:
        cfg.compiler.sdk_mode = args.sdk
    if args.no_tts:
        cfg.voice.tts_enabled = False

    logger = get_logger(cfg.paths.logs)
    logger.info(f"LLM Project :: mode={args.mode} sdk={cfg.compiler.sdk_mode}")

    llm = _select_llm(cfg, args.llm, logger)
    pipeline = Pipeline(cfg, llm, logger, mode=args.mode)
    speaker = Speaker(cfg.voice.espeak_voice, cfg.voice.espeak_speed_wpm,
                      enabled=cfg.voice.tts_enabled)

    # --- one-shot ---------------------------------------------------------
    if args.once is not None:
        outcome = pipeline.process_command(args.once)
        speaker.say(outcome.spoken)
        return 0 if not outcome.errors else 1

    # --- batch ------------------------------------------------------------
    if args.batch:
        lines = Path(args.batch).read_text(encoding="utf-8").splitlines()
        rc = 0
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            print(f"\n=== command: {line} ===")
            outcome = pipeline.process_command(line)
            speaker.say(outcome.spoken)
            if outcome.errors:
                rc = 1
            if outcome.should_exit:
                break
        return rc

    # --- interactive ------------------------------------------------------
    grammar = cfg.paths.root / cfg.voice.grammar_file
    vosk_model = cfg.paths.root / cfg.voice.vosk_model_path
    recognizer = SpeechRecognizer(
        grammar_file=grammar, use_grammar=cfg.voice.stt_use_grammar,
        mic_index=cfg.voice.mic_device_index, force_text=args.text,
        vosk_model_path=vosk_model,
    )
    speaker.say("LLM Project ready.")
    logger.info(f"STT mode: {recognizer.mode}")
    while True:
        text = recognizer.listen("Command")
        outcome = pipeline.process_command(text)
        speaker.say(outcome.spoken)
        if outcome.should_exit:
            break
    return 0


if __name__ == "__main__":
    sys.exit(main())
