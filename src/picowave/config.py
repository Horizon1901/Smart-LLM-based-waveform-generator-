"""Central configuration for PicoWave Assistant.

Defaults live here as a dataclass so the app runs with zero config. An optional
``config/config.yaml`` (if PyYAML is installed) overrides any field. Paths are
resolved relative to the project root so the tree is relocatable.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

# Project root = two levels up from this file: src/picowave/config.py -> root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class Paths:
    root: Path = PROJECT_ROOT
    manufacturer: Path = PROJECT_ROOT / "manufacturer"
    templates: Path = PROJECT_ROOT / "templates"
    generated: Path = PROJECT_ROOT / "generated"
    backup: Path = PROJECT_ROOT / "backup"
    build: Path = PROJECT_ROOT / "build"
    logs: Path = PROJECT_ROOT / "logs"
    mock: Path = PROJECT_ROOT / "mock"

    def ensure(self) -> None:
        for p in (self.generated, self.backup, self.build, self.logs):
            p.mkdir(parents=True, exist_ok=True)


@dataclass
class LLMConfig:
    host: str = "http://localhost:11434"   # local Ollama
    model: str = "qwen2.5-coder:7b"
    # Low temperature for deterministic intent extraction; escalated on retry.
    temperature: float = 0.0
    temperature_retry_step: float = 0.3
    max_retries: int = 3
    request_timeout_s: int = 120


@dataclass
class VoiceConfig:
    # STT: PocketSphinx is tried first; Vosk is a more reliable offline
    # fallback (no acoustic-model directory-layout fragility, prebuilt wheels,
    # no compilation) used automatically when PocketSphinx is unavailable.
    stt_enabled: bool = True
    stt_use_grammar: bool = True          # constrain PocketSphinx to command JSGF
    grammar_file: str = "config/grammar.jsgf"
    mic_device_index: Optional[int] = None
    vosk_model_path: str = "models/vosk-model-small-en-us-0.15"
    # TTS
    tts_enabled: bool = True
    espeak_voice: str = "en"
    espeak_speed_wpm: int = 165


@dataclass
class CompilerConfig:
    # "mock" links the offline shim; "real" links the installed PicoSDK.
    sdk_mode: str = "mock"
    cc: str = "gcc"
    cflags: str = "-O2 -Wall -Wextra"
    # Real PicoSDK locations (Linux defaults from manufacturer configure.ac).
    pico_include: str = "/opt/picoscope/include"
    pico_lib: str = "/opt/picoscope/lib"


@dataclass
class Config:
    paths: Paths = field(default_factory=Paths)
    llm: LLMConfig = field(default_factory=LLMConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    compiler: CompilerConfig = field(default_factory=CompilerConfig)

    # Default acquisition/siggen session parameters (mutated by voice commands).
    default_samples: int = 1024
    default_timebase: int = 8
    default_range_enum: str = "PS2000_5V"

    # Housekeeping: how many generated .c/.csv sets to keep in generated/
    # before older ones are pruned automatically after each successful run.
    max_generated_files: int = 50

    def as_dict(self) -> dict:
        return asdict(self)


def load_config(path: Optional[str] = None) -> Config:
    """Return a Config, overlaying ``config/config.yaml`` if present + PyYAML available."""
    cfg = Config()
    cfg.paths.ensure()

    yaml_path = Path(path) if path else (PROJECT_ROOT / "config" / "config.yaml")
    if not yaml_path.exists():
        return cfg
    try:
        import yaml  # optional dependency
    except ImportError:
        return cfg

    with open(yaml_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    # Shallow, section-wise overlay -- unknown keys ignored on purpose.
    for section in ("llm", "voice", "compiler"):
        if section in data and isinstance(data[section], dict):
            target = getattr(cfg, section)
            for k, v in data[section].items():
                if hasattr(target, k):
                    setattr(target, k, v)
    for k in ("default_samples", "default_timebase", "default_range_enum",
              "max_generated_files"):
        if k in data:
            setattr(cfg, k, data[k])
    return cfg
