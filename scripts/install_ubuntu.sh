#!/usr/bin/env bash
# PicoWave Assistant -- Ubuntu 24.04 LTS setup (offline-capable after this runs).
set -euo pipefail
echo "==> Installing system packages (needs sudo)..."
sudo apt-get update
sudo apt-get install -y \
    build-essential gcc make cmake \
    python3 python3-pip python3-venv \
    espeak-ng \
    swig libpulse-dev libasound2-dev portaudio19-dev

echo "==> Creating Python virtual environment (.venv)..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt || {
    echo "!! pocketsphinx failed to build. The pipeline still runs in --text mode."; }

echo "==> Done. Next:"
echo "   1) ./scripts/setup_ollama.sh        # install + pull the local model"
echo "   2) Install the real PicoSDK from https://www.picotech.com/downloads/linux"
echo "      (only needed to talk to real hardware; --sdk mock works without it)"
echo "   3) ./scripts/run.sh                  # start the assistant"
