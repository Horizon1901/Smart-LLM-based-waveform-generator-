# User Manual

## Starting the assistant

| Command | What it does |
| --- | --- |
| `make voice` | Full voice mode: real scope, Ollama, microphone |
| `make run` | Type commands instead of speaking; mock scope |
| `make demo` | Non-interactive scripted demo, mock everything |
| `./scripts/run.sh --text --sdk real` | Type commands, drive a real scope |
| `./scripts/run.sh --once "acquire data from channel A"` | Single command |

On start you'll hear/see "PicoWave assistant ready." Then speak (or type) a
command. Say **"exit"** to quit.

## What you can say

Phrasing is flexible; these are representative:

**Acquisition**
* "Acquire data from channel A"
* "Capture channel B"

**Signal generation (built-in)**
* "Generate a 1 kHz sine wave"
* "Generate a 2 kHz square wave"
* "Generate a triangle wave"
* "Generate a ramp up wave"

**Arbitrary waveform**
* "Generate an arbitrary sawtooth waveform"
* "Generate a custom triangle waveform"

**Settings (these adjust state; the next acquire/generate uses them)**
* "Set trigger level to 500 millivolts"
* "Set trigger type to falling"
* "Set sample count to 2048"
* "Set timebase to 6"
* "Set frequency to 5 kHz"
* "Set amplitude to 3000"      (peak-to-peak millivolts)
* "Set offset to 200"          (millivolts)

**Other**
* "Help" — lists commands
* "Exit" / "quit" / "stop"

## How settings persist

Settings accumulate. For example:

```
"set sample count to 2048"
"set trigger level to 500 millivolts"
"set trigger type to rising"
"acquire data from channel A"     ← uses 2048 samples + the trigger you set
```

Each spoken setting is confirmed back to you.

## What you get back

For an acquisition the assistant speaks a summary like *"acquired 2048 samples
from channel A, overflow 0"* and writes:

* `generated/acquisition_NNN.c` — the exact program that ran (kept for
  inspection),
* `generated/acquisition_NNN.csv` — every sample: index, time, ADC counts and
  millivolts for both channels.

For signal generation it confirms the waveform, frequency, amplitude and offset,
and the scope's generator output stays on for the configured hold time.

## Where things are

* Generated programs and CSVs: `generated/`
* Compiled binaries: `build/`
* Logs (one JSONL file per session + a rolling app log): `logs/`
* Backups of generated files: `backup/`

## Tips

* In a noisy room, prefer the constrained grammar (default) — it's far more
  accurate than open dictation for these fixed commands.
* If a command is misheard, just say it again; nothing is applied until an intent
  is recognised.
* Running without a scope? Use `--sdk mock` to rehearse commands end to end.
