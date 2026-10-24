# Installation Guide

## 0. Run it right now with nothing installed

The core orchestrator uses only the Python standard library. From the project
root:

```bash
make demo     # batch of commands, mock LLM + mock scope, no deps
make test
```

Everything below is for adding the real voice engines, the local LLM, and real
hardware.

## 1. Ubuntu 24.04 LTS (primary target)

```bash
bash scripts/install_ubuntu.sh
```

This installs `build-essential`, `gcc`, `make`, `cmake`, `espeak-ng`, the
PocketSphinx build prerequisites (`swig`, `libasound2-dev`, `portaudio19-dev`),
creates a `.venv`, and installs `requirements.txt`.

If PocketSphinx fails to build, the assistant still runs in `--text` mode; fix
the mic later without blocking anything else.

## 2. Local LLM (Ollama)

```bash
bash scripts/setup_ollama.sh            # installs Ollama, pulls qwen2.5-coder:7b
# or a different model:
bash scripts/setup_ollama.sh llama3.1:8b
```

Set the model in `config/config.yaml` (`llm.model`) if you change it. The client
auto-detects whether Ollama is reachable and falls back to the rule-based
`MockLLM` if not.

## 3. Real PicoSDK (only for real hardware)

Follow Pico Technology's Linux instructions:
<https://www.picotech.com/downloads/linux>. Install the `libps2000` package; by
default the headers land in `/opt/picoscope/include` and the library in
`/opt/picoscope/lib` (these are the defaults in `config/config.yaml` and match
the manufacturer's `configure.ac`). Then run with `--sdk real`.

Add your user to the group that grants USB access (per Pico's instructions) so
the device can be opened without root.

## 4. Windows (portable path)

The generated C uses the same `#ifdef WIN32` guards as the manufacturer example
(`ps2000.h`, `_stdcall`). To build a generated file on Windows:

* Install the PicoSDK for Windows (provides `ps2000.h` + `ps2000.lib`).
* Build with the included CMake:

  ```bat
  cmake -B build-cmake -DGEN_SOURCE=generated/acquisition_001.c -DUSE_MOCK=OFF ^
        -DPICO_INCLUDE="C:/Program Files/Pico Technology/SDK/inc" ^
        -DPICO_LIB="C:/Program Files/Pico Technology/SDK/lib"
  cmake --build build-cmake
  ```

`espeak-ng` and PocketSphinx both have Windows builds; install them and set the
paths. The Python orchestrator itself is OS-independent.

## 5. Verify

```bash
make test                                   # unit tests
python -m picowave.main --text --sdk mock --once "generate a 1 kHz sine wave"
```

You should see a generated file appear in `generated/`, a successful compile,
mock execution output, and a spoken/console `RESULT:` line.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `compiler not found` | install `gcc` (`sudo apt install build-essential`) |
| `libps2000/ps2000.h missing` in real mode | install the PicoSDK; check `pico_include` in config |
| Ollama "not reachable" | `ollama serve` then `ollama pull <model>` |
| PocketSphinx import error | run in `--text` mode; rebuild with `swig`/`portaudio19-dev` present |
| device exit code 99 | scope not connected or no USB permission; check the Pico udev group |
