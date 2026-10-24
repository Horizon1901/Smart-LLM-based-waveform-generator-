#!/usr/bin/env bash
# Install Ollama and pull the local model used for intent parsing.
set -euo pipefail
MODEL="${1:-qwen2.5-coder:7b}"
if ! command -v ollama >/dev/null 2>&1; then
    echo "==> Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi
echo "==> Starting Ollama service (if not already running)..."
(ollama serve >/dev/null 2>&1 &) || true
sleep 2
echo "==> Pulling model: $MODEL"
ollama pull "$MODEL"
echo "==> Ollama ready with $MODEL."
