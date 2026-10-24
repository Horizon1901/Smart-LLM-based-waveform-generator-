#!/usr/bin/env bash
# LLM Project -- one-shot setup.
#
# Creates a venv INSIDE this project folder, installs the CLI and GUI
# dependencies into it, and runs a few sanity checks so setup problems show up
# here instead of as a confusing runtime error later. Safe to re-run.
#
# Usage:
#   ./setup.sh            # CLI + GUI deps
#   ./setup.sh --cli-only # skip PySide6/matplotlib

set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

CLI_ONLY=0
for arg in "$@"; do
  [ "$arg" = "--cli-only" ] && CLI_ONLY=1
done

echo "== LLM Project setup =="
echo "Project root: $(pwd)"

# --- venv ---------------------------------------------------------------
if [ ! -d venv ]; then
  echo "-- creating venv/"
  python3 -m venv venv
else
  echo "-- venv/ already exists, reusing it"
fi
# shellcheck disable=SC1091
source venv/bin/activate
python3 -m pip install --upgrade pip -q

# --- python deps ----------------------------------------------------------
echo "-- installing requirements.txt"
pip install -r requirements.txt -q
if [ "$CLI_ONLY" -eq 0 ]; then
  echo "-- installing requirements-gui.txt"
  pip install -r requirements-gui.txt -q
fi

# --- system tools (checked, not installed -- avoids surprise sudo) --------
echo "-- checking system tools"
MISSING=()
command -v gcc  >/dev/null 2>&1 || MISSING+=("gcc (sudo apt install build-essential)")
command -v espeak-ng >/dev/null 2>&1 || command -v espeak >/dev/null 2>&1 \
  || MISSING+=("espeak-ng (sudo apt install espeak-ng)")
if ! ldconfig -p 2>/dev/null | grep -qi ps2000; then
  MISSING+=("libps2000 (Pico's Linux SDK -- only needed for --sdk real)")
fi
if ! ldconfig -p 2>/dev/null | grep -qi portaudio; then
  MISSING+=("libportaudio2 (sudo apt install libportaudio2 -- needed for voice input's microphone; the app runs fine without it, just in text mode)")
fi
if [ "${#MISSING[@]}" -gt 0 ]; then
  echo "   Missing (optional depending on what you use):"
  for m in "${MISSING[@]}"; do echo "     - $m"; done
else
  echo "   gcc, espeak-ng, libps2000 all found"
fi

# --- import sanity check ---------------------------------------------------
echo "-- verifying python imports"
PYTHONPATH=src python3 - <<'PY'
import sys
mods = ["picowave.config", "picowave.pipeline", "picowave.llm.client"]
try:
    import picowave.gui  # noqa: F401
    mods.append("picowave.gui")
except Exception as exc:  # noqa: BLE001
    print(f"  (GUI import skipped/failed: {exc})")
for m in mods:
    __import__(m)
    print(f"  OK  {m}")
PY

# --- live voice diagnostic ---------------------------------------------
# Runs the actual PocketSphinx init every time setup runs, so the real
# reason voice is or isn't available is always visible right here -- not a
# separate command to remember to run later.
echo
echo "-- checking voice input (Vosk, or PocketSphinx as fallback + microphone)"
PYTHONPATH=src python3 - <<'PY'
try:
    from pathlib import Path
    from picowave.config import load_config
    from picowave.voice.stt import SpeechRecognizer
    cfg = load_config()
    vosk_model = cfg.paths.root / cfg.voice.vosk_model_path
    rec = SpeechRecognizer(vosk_model_path=vosk_model)
    if rec.mode == "voice":
        print(f"   Voice input is ready ({rec.engine} + microphone OK).")
    else:
        print(f"   Voice input is NOT available: {rec.init_error}")
        print("   The app still works fully in text mode either way.")
        print("   See VOICE_SETUP.md for how to enable it (Vosk is the")
        print("   easiest path -- one model download, no compilation).")
except Exception as exc:  # noqa: BLE001
    print(f"   Could not check voice input: {exc}")
PY

echo
echo "== Setup complete =="
echo "Activate this environment in future terminals with:"
echo "  source venv/bin/activate"
echo
echo "Run the GUI (offline, no hardware/model needed):"
echo "  PYTHONPATH=src python3 -m picowave.gui --sdk mock --llm mock"
echo
echo "Run the GUI against real hardware + Ollama:"
echo "  PYTHONPATH=src python3 -m picowave.gui --sdk real --llm ollama"
echo
echo "Run the CLI:"
echo "  PYTHONPATH=src python3 -m picowave.main --text --sdk mock --llm mock"
