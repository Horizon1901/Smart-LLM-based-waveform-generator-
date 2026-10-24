# PicoWave Assistant

An **offline, voice-controlled PicoScope 2000-series controller**. You speak a
command; a local speech engine transcribes it; a local LLM turns it into a
structured intent; the system generates a brand-new C program built on Pico
Technology's own `ps2000` example, compiles it, runs it against the scope, and
speaks the result back — with **no cloud services at any stage**.

```
speak → PocketSphinx (STT) → Ollama LLM (intent) → C code generation
      → auto-compile → auto-run on PicoScope → eSpeak NG (TTS)
```

## Why it's built this way (important design note)

The brief asks the LLM to "generate a new C file" *and* to "not invent PicoSDK
code." A 7B local model writing driver C freehand will hallucinate API
signatures and fail to compile most of the time. So the default path splits the
work along the grain of what each component is good at:

* **The LLM extracts a structured *intent*** (action + parameters) from speech —
  a task small models do reliably.
* **A deterministic generator** assembles a complete, genuinely new
  `generated/acquisition_NNN.c` from fragments derived from the manufacturer's
  `ps2000Con.c`, using only real `ps2000_*` API calls. It therefore **always
  compiles**.

A freehand path (`--mode llm-freeform`) is still included and wired through the
compile → capture-errors → rollback → retry loop, but it is opt-in. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the full rationale.

## Quickstart (offline, no hardware, no model server)

```bash
# From the project root:
make demo        # runs a batch of spoken-style commands end to end
make test        # unit tests
make run         # interactive: type commands, mock scope
```

`make demo` uses the **mock PicoSDK** (`mock/`) so the whole generate → compile →
run loop works on a laptop with no PicoScope attached — matching a
develop-at-home / demo-on-hardware workflow.

## Real hardware

```bash
make setup                       # system + Python deps (Ubuntu 24.04)
make ollama                      # install Ollama, pull qwen2.5-coder:7b
# install the real PicoSDK: https://www.picotech.com/downloads/linux
make voice                       # full voice mode against a real scope
```

## Supported commands (v1)

Acquire from channel A / B · generate 1 kHz sine · 2 kHz square · triangle ·
set trigger level · set trigger type · set sample count · set timebase ·
generate arbitrary waveform · set signal-generator frequency · set amplitude ·
set offset voltage. Adding more is a template + an action (see
[DEVELOPER.md](DEVELOPER.md)).

## Documentation

* [INSTALL.md](INSTALL.md) — full installation, including Windows notes
* [ARCHITECTURE.md](ARCHITECTURE.md) — modules, data flow, diagrams
* [DEVELOPER.md](DEVELOPER.md) — how to extend it
* [USER_MANUAL.md](USER_MANUAL.md) — day-to-day usage
* [diagrams/](diagrams/) — flowcharts and component diagrams

## Layout

```
manufacturer/   Pico Technology ps2000 example, UNTOUCHED (the base project)
templates/      manufacturer-derived C templates the generator fills
generated/      one new .c per command, never overwritten (kept for inspection)
mock/           offline ps2000 shim (dev/test only; not used on real hardware)
src/picowave/   the orchestrator (config, logging, llm, codegen, compiler,
                executor, voice, backup, pipeline, main)
config/         config.yaml + PocketSphinx grammar
scripts/        install / ollama / run / demo
docs/           this documentation
tests/          unit tests + sample command batch
```
