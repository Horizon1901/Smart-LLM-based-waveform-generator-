# PicoWave Assistant — Project Overview

## What it is

An offline, natural-language-controlled desktop application for the PicoScope
2204A oscilloscope. You type or speak a plain-English command; a local LLM
(Ollama) turns it into a structured intent; the app generates C code from
manufacturer-verified templates, compiles it, and runs it against the real
device (or an offline mock for development). Results — waveforms and captured
data — are displayed live in the desktop GUI. Everything runs fully offline:
no cloud LLM, no internet dependency once set up.

It has two interfaces to the same backend:
- **Desktop GUI** (`picowave.gui`) — the primary interface: command box, voice
  input, live result plots, generated-code viewer, CSV viewer, console.
- **CLI** (`picowave.main`) — text/voice loop in the terminal, useful for
  quick scripted tests or headless use.

## What it actually does, end to end

1. You give a command (typed, spoken, or via voice button).
2. The LLM (or the offline rule-based parser) converts it into a structured
   intent: an action plus parameters.
3. Parameters merge into a **persistent session state** — settings you change
   stay in effect until you change them again, across commands.
4. For any action that touches hardware, the app renders a C program from a
   template, compiles it with `gcc`, and runs it. The program talks to the
   PicoScope through the real `libps2000` driver (or the bundled mock driver
   in `--sdk mock`).
5. The result — a generated waveform, a captured dataset, or an updated
   setting — is reported back in speech/text and shown in the GUI.

### The four things it can do to the hardware

| Action | What it does | Produces |
|---|---|---|
| **Generate** (siggen) | Outputs a built-in waveform (sine/square/triangle/ramp) from the AWG output | A physical signal on the generator pin; no data file (nothing was captured) |
| **Acquire** | Captures a block of samples from channel A, B, or both | A real CSV of captured voltages, shown as a plot + table |
| **Generate + Capture** (measure) | Generates a waveform **and** captures it in one continuous, uninterrupted device session | A real CSV of the actual generated signal, looped back through a cable — this is the only way to see your own generated signal as real captured data |
| **Arbitrary waveform** | Outputs a custom-shaped waveform (sine/square/triangle/sawtooth) via the AWG buffer | Physical signal, like siggen |

### Why "Generate + Capture" exists as its own action
Running "Generate" then "Acquire" as two separate commands can never show a
real signal — each command is a separate program, and the app waits for that
program to fully exit before you get control back. The generate program closes
the device (stopping the output) before it exits, so by the time you could
issue "Acquire," the signal is already gone. "Measure" fixes this by opening
the device once, starting the generator, and capturing on that same
still-open connection — the signal is guaranteed live for the whole capture.

## Parameters you can change (by voice or text)

All of these persist across commands until changed again. Say a value
absolutely ("set frequency to 5000 Hz") or relatively ("increase the
frequency", "double the amplitude", "decrease offset by 200 mV").

| Parameter | What it controls | Typical values / bounds |
|---|---|---|
| `channel` | Which input channel to acquire from | A, B, or BOTH |
| `range_enum` | Input voltage range (affects scaling + clipping) | 10 mV – 50 V, e.g. "set channel A range to 5 V" |
| `n_samples` | Samples per capture | 16 – 32000 (real single-channel device max ≈ 8000; dual-channel auto-capped ≈ 4000) |
| `timebase` | Sample rate/spacing (higher = slower sampling, longer time window for same sample count) | 0 – 23 |
| `oversample` | Hardware oversampling factor | 1 – 256 |
| `trigger_enabled` / `trigger_level_mv` / `trigger_direction` | Whether to wait for a trigger edge before capturing, at what level, rising or falling | e.g. "set trigger level to 300 mV", "enable rising trigger" |
| `siggen_wave` | Built-in waveform shape | sine, square, triangle, ramp_up, ramp_down |
| `siggen_freq_hz` | Generator frequency | 1 Hz – 100 kHz |
| `amplitude_mvpp` | Generator peak-to-peak amplitude | 0 – 4000 mV (±2 V) |
| `offset_mv` | Generator DC offset | −2000 – 2000 mV |
| `arb_shape` | Arbitrary-waveform shape | sine, square, triangle, sawtooth |
| `hold_ms` | How long a standalone "generate" holds output before auto-closing | 0 – 30000 ms |
| `dc_coupled` | AC/DC coupling on the input | on/off |

All values are clamped to device-safe bounds automatically, so an out-of-range
request gets pulled back into a safe value rather than damaging anything.

## Example commands, by category

**Generation:** "Generate a 1 kHz sine wave" · "Generate a square wave at
3000 Hz" · "Generate a triangle wave" · "Generate a ramp up at 500 Hz"

**Combined generate+capture:** "Generate a sine wave at 2000 Hz and capture
it" · "Generate a square wave and measure both channels" · "Loopback test a
5 kHz sine wave"

**Acquisition:** "Acquire 1024 samples from channel A" · "Acquire from both
channels" · "Capture 4096 samples from channel B"

**Settings:** "Set trigger level to 300 mV" · "Enable rising trigger" · "Set
timebase to 10" · "Set channel A range to 5 V" · "Set amplitude to 3 volts"

**Relative adjustments:** "Increase the amplitude" · "Double the frequency" ·
"Decrease offset by 200 mV" · "Lower the frequency by 20 percent"

**Meta:** "Help" · "Exit"

## Project layout — what each file/folder does

```
LLM-Pico-project--main/
├── setup.sh                    One-shot environment setup (venv + deps + checks)
├── FIXES_APPLIED.md            Changelog of fixes made across this project's history
├── PROJECT_OVERVIEW.md         This file
├── requirements.txt            Core CLI dependencies
├── requirements-gui.txt        Desktop GUI dependencies (PySide6, matplotlib, numpy)
├── config/
│   ├── config.yaml              All tunable settings (LLM model, voice, compiler, defaults)
│   └── gui_settings.json        Auto-saved: last SDK/LLM choice + session state (created at runtime)
├── templates/                   C source templates (the "deterministic core" — the LLM never writes device code)
│   ├── siggen.c.tmpl              Built-in waveform generation
│   ├── acquire.c.tmpl             Block capture (single or dual channel)
│   ├── measure.c.tmpl             Combined generate+capture, one session
│   └── arb.c.tmpl                 Arbitrary waveform generation
├── mock/                        Offline simulated PicoSDK (for --sdk mock)
├── manufacturer/                Pico's original reference C examples (source of truth for the templates)
├── generated/                   Output: generated .c files + captured .csv files (auto-pruned, keeps last ~50)
├── logs/                        Structured JSONL session logs (one file per run)
└── src/picowave/
    ├── main.py                   CLI entry point (python -m picowave.main)
    ├── pipeline.py                The orchestrator: intent -> state -> codegen -> compile -> execute -> result
    ├── intent.py                  Action enum, SessionState (all the parameters above), Intent parsing
    ├── config.py                  Config dataclasses + config.yaml loader
    ├── logger.py                  Structured logging + event bus (feeds the GUI console)
    ├── codegen/
    │   ├── generator.py             Renders templates into real .c files from the current state
    │   └── freeform.py               Optional (non-default) mode: LLM writes C directly, less tested
    ├── compiler/builder.py        Invokes gcc to compile the generated .c
    ├── executor/runner.py         Runs the compiled binary, captures output, parses the RESULT line
    ├── backup/manager.py          Snapshot/rollback support for freeform mode
    ├── llm/
    │   ├── client.py                OllamaClient (real LLM) + MockLLM (offline rule-based parser)
    │   └── prompts.py                The system prompt that defines the JSON intent schema
    ├── voice/
    │   ├── stt.py                    Speech-to-text via PocketSphinx (falls back to typed input)
    │   └── tts.py                    Text-to-speech via espeak-ng (falls back to console text)
    └── gui/                       Desktop application (PySide6 + matplotlib)
        ├── app.py                    Bootstraps the backend and launches the window
        ├── __main__.py               `python -m picowave.gui` entry point + CLI flags
        ├── main_window.py            Main window: layout, routing, status badges, settings
        ├── state_persistence.py     Save/load SDK mode, LLM choice, session state to disk
        ├── log_bridge.py             Streams backend log events into the on-screen console
        ├── waveform_math.py          Ideal-waveform math + CSV reading + disconnected-input heuristic
        ├── theme.py                  Dark UI theme
        ├── panels/                   Command input panel, console panel
        ├── tabs/                     Result plot tab, Generated-C tab, CSV viewer tab
        ├── syntax/                   C syntax highlighter for the code tab
        ├── dialogs/                  Settings dialog (SDK/LLM switch)
        └── workers/                  Background threads: command execution, voice I/O, status polling
```

## How to run it

```bash
cd LLM-Pico-project--main
./setup.sh                      # one-time: venv + all dependencies
source venv/bin/activate        # every new terminal session

# Offline, no hardware, no LLM server needed:
PYTHONPATH=src python3 -m picowave.gui --sdk mock --llm mock

# Real hardware + real LLM:
PYTHONPATH=src python3 -m picowave.gui --sdk real --llm ollama

# CLI instead of GUI:
PYTHONPATH=src python3 -m picowave.main --text --sdk real --llm ollama
```
SDK mode and LLM choice are remembered automatically after the first run — an
explicit flag always overrides the saved value; omitting flags reuses the last
choice.

## Honest current limitations

- **No live/streaming view.** Every result is a snapshot from a single
  command, not a continuously updating trace — a deliberate design choice.
- **Sample ceiling.** ~8000 samples/channel single, ~4000 dual — the real
  device's single-block limit; going beyond it needs streaming mode, not
  implemented.
- **Device opens fresh per command.** Simple and safe, but no persistent
  connection between commands.
- **LLM hardware fit.** A 7B model is close to the edge on a 7 GB RAM / 6 GB
  VRAM laptop — reliable once warmed and tuned (CPU-only, sane keep-alive),
  but cold loads or long idle gaps can still cause noticeable slowdown.
  `--llm mock` bypasses this entirely with no loss of command-parsing
  capability for the fixed vocabulary this project uses.
- **Voice verified structurally, not acoustically** — STT is timeout-guarded
  and TTS is exception-safe, but real-room recognition accuracy depends on
  your mic/PocketSphinx setup and hasn't been tuned beyond the defaults.
