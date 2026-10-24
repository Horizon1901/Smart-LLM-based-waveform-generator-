# PicoWave Assistant — setup (CLI + desktop GUI in one project)

This is the complete project: your existing backend plus the integrated PySide6
desktop GUI. Nothing needs to be merged.

## 1. Install
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt         # core CLI
    pip install -r requirements-gui.txt      # desktop GUI (PySide6, matplotlib, numpy)

## 2. Run the GUI
    PYTHONPATH=src python3 -m picowave.gui                 # offline (mock SDK)
    PYTHONPATH=src python3 -m picowave.gui --sdk real --llm ollama   # real 2204A

## 3. Run the CLI (unchanged)
    PYTHONPATH=src python3 -m picowave.main --text --sdk mock --llm mock

## What the GUI does
- Type or speak a command; it runs your real pipeline (LLM -> C -> compile ->
  execute) on a background thread.
- Result tab: ideal waveform for signal generation, real CSV plot for acquisition.
- Generated C tab: the generated source with syntax highlighting (Copy / Save).
- CSV viewer: table + plot of the newest capture.
- Console: LLM / compile / execute / SDK activity.
- Menu -> Settings: switch SDK mode and LLM backend live.
- Relative commands work ("increase the amplitude", "double the frequency").

## Notes
- Requires Ollama running with the model pulled, OR use --llm mock offline.
- Voice needs PocketSphinx + a mic; espeak-ng for spoken results. Without them,
  the app runs fine in text mode.
