"""LLM Project -- offline voice-controlled PicoScope 2000 code generator.

Pipeline:  speech -> PocketSphinx or Vosk (STT) -> Ollama LLM (intent) -> deterministic
C code generation from manufacturer-derived templates -> auto compile ->
auto run against the PicoScope -> eSpeak NG (TTS).

Everything runs locally; no cloud services are used.
"""

__version__ = "1.0.0"
