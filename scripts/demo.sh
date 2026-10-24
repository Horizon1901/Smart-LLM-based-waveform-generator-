#!/usr/bin/env bash
# Offline demo: runs the sample command batch with the mock LLM + mock SDK.
# No microphone, no Ollama, no PicoScope required.
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONPATH="src:${PYTHONPATH:-}"
python3 -m picowave.main --batch tests/sample_commands.txt --sdk mock --llm mock --no-tts
