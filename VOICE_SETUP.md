# Voice setup

Voice input is optional -- the app runs fully in text mode with no setup
below. This is only needed if you want the Voice button / spoken commands
to work.

## How engine selection works

`setup.sh` and the app itself try, in order:

1. **Vosk** -- tried first, if a model has been downloaded (one-time, see
   below). Chosen as primary because it does open-vocabulary recognition
   from its own trained model rather than a hand-maintained grammar checked
   word-by-word against a fixed dictionary -- PocketSphinx's grammar has
   broken outright (not just recognized poorly, but failed to even start)
   multiple times across this project's development whenever its command
   vocabulary grew faster than the grammar file was kept in sync with
   PocketSphinx's bundled dictionary.
2. **PocketSphinx** -- automatically, only if Vosk did not work (no model
   downloaded, or the package itself is unavailable). Can be more accurate
   than Vosk once its grammar is valid; its own grammar file is now
   validated for real at startup, with automatic fallback to open dictation
   if it ever fails to compile again, rather than crashing.
3. **Text mode** -- if neither is available. Nothing breaks; you just type
   instead of speak.

Both `pocketsphinx` and `vosk` are already listed in `requirements.txt`, so
`./setup.sh` installs both packages either way. The only manual step is
downloading a Vosk *model* -- Vosk's model data isn't pip-installable, unlike
PocketSphinx's.

## One-time Vosk model download

Small English model (~40 MB, good accuracy for short commands):

```bash
mkdir -p models
curl -LO https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip
unzip vosk-model-small-en-us-0.15.zip -d models/
rm vosk-model-small-en-us-0.15.zip
```

This must produce `models/vosk-model-small-en-us-0.15/` directly under the
project root (matching the default `voice.vosk_model_path` in
`config/config.yaml`). If you'd rather keep the model elsewhere, change that
config value to point at it.

Larger, more accurate models are available at
https://alphacephei.com/vosk/models if the small model's accuracy isn't
enough for your use case -- any of them work, just update
`vosk_model_path` to match the folder name you extract.

## Confirming it worked

```bash
./setup.sh
```

The final lines report the real status directly:

```
-- checking voice input (Vosk, or PocketSphinx as fallback + microphone)
   Voice input is ready (vosk + microphone OK).
```

or, if Vosk isn't set up (no model downloaded yet) but PocketSphinx is:

```
   Voice input is ready (pocketsphinx + microphone OK).
```

or, if neither is available, the exact reason for each is printed so you
know which one to fix (or that you just haven't downloaded a Vosk model yet).

In the app itself, the top-right status badge shows which engine is active,
e.g. "voice: mic (vosk) + speech ready".

## System dependencies either engine needs

Both PocketSphinx's and Vosk's microphone capture go through the same
`sounddevice` package, which needs the system PortAudio library:

```bash
sudo apt install libportaudio2
```

Without this, `import sounddevice` fails immediately and neither engine can
ever work, regardless of which Python packages or models are installed.

## Bluetooth headsets/earbuds: a common, separate gotcha

If voice input isn't picking up anything at all when using a Bluetooth
headset or earbuds, this is almost always an OS-level audio *profile* issue,
unrelated to PocketSphinx, Vosk, or this project's code entirely: most
Bluetooth headsets support two connection profiles --

- **A2DP** (high-quality stereo, output only) -- the default for most media
  playback, and the microphone simply does not function in this mode at the
  protocol level, regardless of what software tries to use it.
- **HSP/HFP** (headset/hands-free, lower quality, bidirectional) -- required
  for the microphone to work at all, but Linux does not always switch to it
  automatically just because an application wants to record.

Check and fix the active profile:

```bash
# List Bluetooth audio cards and their available profiles
pactl list cards short
pactl list cards | grep -A 20 bluez

# Switch to a profile that enables the microphone (name varies by device --
# look for one containing "handsfree" or "headset" in the profile list above)
pactl set-card-profile <card-name> headset-head-unit
```
Or use a GUI: `pavucontrol` -> Input Devices tab -> confirm the Bluetooth
device is selected and showing input level movement while you speak, and
Configuration tab -> confirm the card is set to an HSP/HFP ("headset")
profile, not A2DP.

Confirm capture is actually reaching Python, independent of recognition,
before troubleshooting PocketSphinx/Vosk further:

```bash
python3 -c "
import sounddevice as sd
import numpy as np
print('Recording 3 seconds -- speak now...')
rec = sd.rec(int(3*16000), samplerate=16000, channels=1, dtype='int16')
sd.wait()
print('Peak level:', np.abs(rec).max(), '(should be well above ~500 if your voice was captured)')
"
```
If the peak level stays near zero while you're clearly speaking, this is a
device/profile problem to fix at the OS level (above) -- no change to this
project's code can compensate for the microphone not delivering audio at all.
If it shows a real level, capture is working and any remaining issue is on
the recognition side (wrong engine active, phrasing not matching the
PocketSphinx grammar, etc.) -- see the sections above.

To point the app at a specific input device explicitly (useful once a
Bluetooth device sometimes isn't the OS default), list devices and set the
index in `config/config.yaml` under `voice.mic_device_index`:

```bash
python3 -c "import sounddevice as sd; print(sd.query_devices())"
```
