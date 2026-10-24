# Fixes applied in this pass

## Dual-channel capture (explicit request)
- `intent.py`: SessionState.channel now accepts "A" | "B" | "BOTH". n_samples
  auto-caps to ~4000 when BOTH is selected (shared block buffer).
- `llm/prompts.py`, `llm/client.py`: LLM/mock parser recognize "both channels",
  "channel A and B", etc.
- `codegen/generator.py`, `templates/acquire.c.tmpl`: enables both channels,
  prints/reports both, writes real data into both CSV columns. Fixed a
  substitution-ordering bug found while testing this (range index wasn't
  resolving inside the per-channel print block).
- Verified: both CSV columns carry real non-zero data on a dual-channel
  capture; single-channel behavior unchanged (regression-tested).

## Clear error messages (was: generic "reported an error")
- `pipeline.py`: exit codes 95-99, 124, 126 now map to specific, actionable
  spoken text (e.g. "That capture doesn't fit in one block on this device...").

## CSV/generated-file retention
- `codegen/generator.py`: `prune_old(keep=N)`, called after every successful
  run. New `Config.max_generated_files` (default 50).

## Settings persistence across restarts
- New `gui/state_persistence.py`. SDK mode, LLM choice, and full session
  state save to `config/gui_settings.json` on settings-change and window
  close; restored automatically on next launch.

## Real bug fix: GUI ignored config.yaml
- `gui/app.py` was building `Config()` directly (bypassing config.yaml
  overrides entirely) and referencing a nonexistent `cfg.llm.timeout_s`
  field. Now uses `load_config()` and the correct `request_timeout_s`.

## Disconnected/noise-input hint
- `gui/waveform_math.py`: `looks_disconnected()` heuristic. Result and CSV
  tabs now flag a flat/near-zero channel with a visible warning caption.

## Setup automation
- New `setup.sh`: creates venv, installs both requirement files, checks for
  gcc/espeak-ng/libps2000, runs an import sanity check.

## Automated GUI tests
- New `tests/test_gui_smoke.py`, 9 pytest cases (window build, siggen plot,
  single/dual-channel acquire, relative commands, oversized-request handling,
  code tab, settings round-trip). Skips cleanly without PySide6.

## Verified before packaging
- All 8 original backend tests: PASS
- All 9 new GUI smoke tests: PASS
- CLI regression (siggen, single-channel, dual-channel, relative, exit): PASS
- Dual-channel CSV has real data in both columns (CLI + GUI paths): PASS
- Exit-98 now surfaces a clear message instead of the old generic one: PASS

## Deliberately not attempted (see prior discussion)
- Device-opened-per-command architecture change, and a combined
  generate+capture command -- both need real design work, not a quick edit.
- Live/streaming view, capture beyond the single-block sample ceiling -- these
  were the explicit re-scope items set aside earlier in the project.
- LLM memory/hardware limits, real voice/TTS verification -- hardware-
  dependent, not fixable in code.

## Follow-up fix: explicit --sdk/--llm was silently overridden by saved settings
Found via real hardware testing: `--sdk real` was coming up as "mock" because
the newly-added settings-persistence restore ran *after* window construction
and always applied the saved value, regardless of what was explicitly passed
on the command line. An earlier `--sdk mock` test session had saved "mock",
and it silently won over a later explicit `--sdk real`.

Fixed by:
- `gui/__main__.py`: `--sdk`/`--llm` now default to `None` instead of a
  concrete value, so "not specified" is distinguishable from "specified".
- `gui/app.py`: resolution now happens once, in `run()`, before the pipeline
  or window are built -- an explicit value always wins; `None` falls back to
  the saved value, or the original default if nothing was ever saved.
- `gui/main_window.py`: removed the old post-construction restore, which was
  the actual source of the override (it always re-applied the saved value).
- Added `tests/test_gui_smoke.py::test_explicit_sdk_flag_overrides_saved_value`,
  a regression test that reproduces this exact scenario (save "mock", then
  request "real") so it can't silently return.

Verified: explicit `--sdk real` now stays "real" even with a saved "mock"
present; omitting `--sdk` entirely still correctly falls back to the last
saved choice; all 8 backend + 10 GUI tests pass (18 total).

## Fix: generate-then-capture race condition (was architecturally unwinnable)
Root cause, found while testing on real hardware: "Generate" and "Acquire" are
each a separate compiled program, and the executor's subprocess call blocks
until that program *fully exits*. The siggen program's hold-then-close happens
*inside* that blocked call -- so by the time control returns to the user, the
device has already closed and the output has already stopped. There was no
window afterwards to "capture in time"; more hold time or faster clicking
could never have fixed it.

Fix: a new combined action, `measure` (new `templates/measure.c.tmpl`,
`Action.MEASURE`, `_render_measure`). It opens the device once, starts the
signal generator, captures a block on the SAME still-open handle, and only
then closes -- so the signal is guaranteed live for the entire capture.
Triggered by natural phrasing: "generate a sine wave and capture it",
"generate and measure both channels", "loopback test the square wave", etc.
The old separate `siggen` then `acquire` commands still exist for cases where
you only want one or the other (e.g. probing with an external scope).

Verified: real (non-zero) data captured in the same run that generated the
signal, both single- and dual-channel; natural-language phrasing correctly
routes to `measure` through the full pipeline.

## Fix: STT could hang the mic button forever
PocketSphinx's `LiveSpeech` has no built-in overall timeout -- silence,
background noise, or unclear speech could block `listen()` indefinitely, with
no way to cancel from the GUI (`SttWorker` had no timeout at all). Fixed by
running the actual recognition in a bounded, joined daemon thread; a stuck
listen() now reports a clear "no speech detected, try again" instead of
leaving the Voice button stuck. Verified with a worker that never returns --
now times out cleanly in ~1s instead of hanging.

## Added: voice status visibility
New titlebar badge shows whether the mic (PocketSphinx) and speech output
(espeak) are actually available, instead of the "Speak results" checkbox and
Voice button silently doing nothing if the underlying engines are missing.

## Verified before packaging (this round)
- 8 backend tests + 12 GUI tests (2 new: measure action produces real data;
  STT hang guard times out cleanly): all pass.
- CLI regression covering measure + dual-channel + relative commands: pass.

## Fix: parameter changes (amplitude, frequency, etc.) didn't visibly update the plot
Two separate real bugs, both reported as "I change a setting and see no
difference":

1. **The Result tab never redrew after a settings-only command.** Both
   absolute ("set frequency to 5000 Hz") and relative ("increase the
   amplitude") commands only update `SessionState` -- there was no code path
   that told the plot to redraw after them. The on-screen waveform silently
   went stale the instant you changed anything; you'd only see the new value
   if you happened to re-run a full "generate" afterwards. Fixed in
   `main_window.py`: the Result tab now tracks whether it's showing a live
   ideal-waveform view, and a settings-only command quietly redraws it with
   the fresh values (no tab-switch, so it doesn't yank focus).

2. **The waveform display window always showed exactly 4 cycles, at any
   frequency.** `ideal_waveform()` set the plotted time span to `4 / freq`,
   so the x-axis auto-scaled to fit exactly 4 wiggles every time -- meaning
   1 kHz and 2 kHz looked like the same picture (4 wiggles filling the same
   width); only the axis tick numbers differed, easy to miss at a glance.
   Fixed in `waveform_math.py`: the window is now a fixed duration (5 ms by
   default, bounded between roughly 2 and 20 visible cycles at the extremes),
   so doubling the frequency now visibly doubles the cycle density in the
   same window instead of just rescaling the axis.

Verified: "increase the amplitude" now changes the plotted line data
immediately without re-running generate; 1 kHz vs 2 kHz now produce visibly
different cycle counts in the same fixed window (confirmed via zero-crossing
count, not just eyeballing). Two new permanent regression tests added.

## Verified before packaging (this round)
- 8 backend tests + 14 GUI tests (2 new: set_param live-redraw, frequency
  visual distinguishability): all pass, 22 total.

## Fix: voice input was unconditionally disabled, regardless of mic/PocketSphinx
Root cause: `SpeechRecognizer.mode` returns `"voice"` on a successful
PocketSphinx initialisation (never the literal string `"pocketsphinx"`), but
`main_window.py` had three places comparing against `== "pocketsphinx"` /
`!= "pocketsphinx"` -- a value that can never actually occur. The result: the
Voice button always showed "Voice input needs PocketSphinx and a microphone"
and the status badge always showed "no mic", *even with a working microphone
and a correctly installed PocketSphinx*. This was a pure string-comparison
bug, unrelated to any actual hardware or environment problem -- plugging in a
mic could never have fixed it.

Fixed: all three checks now compare against `"voice"`, matching what
`SpeechRecognizer.mode` actually returns. Verified with both a
recognizer reporting a working mic (voice input now launches correctly, badge
shows "ready") and one reporting no engine at all (still correctly shows the
"needs PocketSphinx" message) -- so the genuinely-unavailable case still
degrades gracefully, only the false-positive block is gone.

## Verified before packaging (this round)
- 8 backend tests + 15 GUI tests (1 new: voice input not blocked when the
  recognizer actually works): all pass, 23 total.

## Fix: PocketSphinx failed with "does not contain acoustic model definition 'mdef'"
Surfaced immediately after the previous voice-input fix let the app actually
attempt to start PocketSphinx for the first time. Root cause: `stt.py`
constructed the wrong paths to the bundled speech model. The `pocketsphinx`
PyPI package lays its data out as:
  `<model_path>/en-us/en-us.lm.bin`
  `<model_path>/en-us/cmudict-en-us.dict`
  `<model_path>/en-us/en-us/mdef`  (the real acoustic model directory,
                                     nested one level deeper -- easy to miss
                                     since the parent is also named "en-us")
All three paths being constructed (`hmm`, `lm`, `dic`) were missing the outer
`en-us/` folder level, and `hmm` was additionally missing the inner nesting.

Reproduced directly: initializing a real PocketSphinx `Decoder` with the old
paths threw the exact error from the field report ("...does not contain
acoustic model definition 'mdef'"); the corrected paths initialize
successfully. Fixed in `voice/stt.py`.

## Verified before packaging (this round)
- 8 backend tests + 15 GUI tests: pass, 23 total (unchanged by this fix,
  which was verified directly against a real PocketSphinx Decoder instead,
  since this bug only manifests with the actual pip package installed).

## New feature: "process" -- analyze + plot the most recent capture
A new action, separate from acquisition itself:

    Acquire 1024 samples from channel A
    Process

"Process" takes no parameters and needs no hardware -- it finds the newest
capture already on disk (stateless: works correctly even across an app
restart, by scanning generated/ for the highest-numbered acquisition_*.csv),
then:
  - Computes real measurements per channel with data: peak-to-peak, mean,
    min/max, RMS, and an estimated dominant frequency (zero-crossing method).
    Verified against known synthetic ground truth (1000 Hz / 2000 mVpp sine ->
    estimated within ~2%).
  - Spawns real gnuplot (`gnuplot -p`, detached, non-blocking) in its own
    window, reading the CSV directly -- verified end-to-end against a real
    installed gnuplot 6.0, including validating the exact generated script
    parses and plots with no errors. Degrades to a clear message (not a
    crash) if gnuplot isn't installed.
  - ALSO updates the app's own Result/CSV tabs with the same capture, so both
    the external gnuplot window and the built-in plot show it.

New files: measurements.py (pure, backend-level -- works from CLI or GUI),
gnuplot_export.py (script generation + detached subprocess launch).
Signal generation is unchanged and still fully available; it's just no longer
the primary focus of this workflow.

Natural-language triggers: "process", "process it", "analyze it", "analyse",
"show the results", "show me the output", "plot it".

## Verified before packaging (this round)
- 16 backend/process tests (8 new: CSV discovery, measurement accuracy vs
  ground truth, flat-channel skipping, gnuplot script correctness -- both
  structurally and against a real installed gnuplot binary, full pipeline
  round-trip, no-prior-capture edge case) plus 16 GUI tests (1 new: process
  routes to both the Result and CSV tabs): 32 total, all pass.
- CLI regression: generate+capture -> process -> acquire both channels ->
  process again (correctly re-targets the newest capture) -> help -> exit.

## Fix: PocketSphinx init failures were silently discarded
`SpeechRecognizer._try_init_pocketsphinx` used a bare `except Exception:
self._mode = "text"` -- whatever the real failure was (missing package,
missing system library, broken model install, anything) got thrown away
with no trace, so "pocketsphinx isn't found" reports were impossible to
diagnose from the app's behaviour alone. Fixed: the real exception is now
captured as `recognizer.init_error` and surfaced in two places -- the Voice
button's guard message, and a tooltip on the voice status badge -- so the
actual reason is visible instead of a generic message every time, regardless
of cause. Verified with a simulated ModuleNotFoundError.

## New feature: waveform shape classification
Extends `process`: after measurements, each channel's captured signal is
classified as sine, square, triangle, or "none of the above" -- e.g.
"Channel A: looks like a square wave (96% match), ...".

This is deterministic signal analysis, not an LLM guess -- LLMs are
unreliable at numeric pattern recognition over thousands of raw samples, and
this matches the project's existing philosophy (LLM parses intent, code does
the actual work). The real signal is detrended, amplitude-normalised, and
correlated against ideal reference shapes -- swept across both phase offset
(the real signal's phase is unknown) and a small neighborhood around the
estimated frequency (frequency estimation has real, if small, error that
compounds into large phase drift over many cycles). A shape is only reported
if its best correlation clears 85%; otherwise "does not clearly match sine,
square, or triangle" is the honest answer, not a forced low-confidence guess.

Verified against synthetic ground truth: all three shapes self-classify
correctly at 95-100% confidence across multiple phase offsets; pure noise is
correctly rejected; robust to up to 15% realistic measurement noise. Caught
and fixed a real bug during development -- the initial version correlated
against a single exact frequency, so the ~4% error typical of the frequency
estimator was enough to break classification of a genuinely correct signal;
fixed by searching a small frequency neighborhood, not just phase.

## Verified before packaging (this round)
- 19 backend/process tests (3 new: phase-invariant classification of all
  three known shapes, noise correctly rejected, robustness to realistic
  frequency-estimation error) plus 17 GUI tests (1 new: pocketsphinx
  init_error capture): 36 total, all pass.
- CLI regression: generate+capture -> process (correctly reports "does not
  match" on the mock SDK's non-periodic placeholder data, which is the
  honest answer -- classification is expected to work correctly on real
  hardware captures of real generated signals).

## Fix: PocketSphinx voice input failing with no clear reason (real root cause)
Traced to the actual mechanism this time, reproduced directly (not
simulated): pocketsphinx 5.x's LiveSpeech uses `sounddevice` to open the
microphone -- NOT `pyaudio`, which is what older tutorials assume.
Critically, `pip install sounddevice` only installs the Python wrapper; the
underlying PortAudio C library is a SEPARATE system package. If it's
missing, `import sounddevice` fails immediately, but that import previously
only happened lazily inside `LiveSpeech()` the moment someone clicked Voice
-- surfacing as a raw, easy-to-miss runtime exception rather than a clear
reason at startup.

Fixed:
- `stt.py` now checks for sounddevice/PortAudio proactively during
  `_try_init_pocketsphinx()`, with a specific message: "microphone audio
  backend unavailable... try: sudo apt install libportaudio2".
- `setup.sh` now checks for `libportaudio2` alongside its other system checks,
  and runs a LIVE voice diagnostic every time setup runs, printing the real
  status directly -- not a separate command to remember to run later.
- `requirements.txt`'s misleading "optional" label on sounddevice is fixed --
  it's required for LiveSpeech to function at all.

Verified by reproducing the exact failure directly (this sandbox genuinely
lacks PortAudio) and confirming the new code catches and reports it clearly,
plus two permanent regression tests (using sys.modules injection rather than
patching the global import hook, which is unsafe in a multi-threaded Qt test
suite -- caught and fixed a real test-suite crash this caused during
development).

## New feature: multi-file "process" with verbal gnuplot control
Extends "process" to handle exactly this kind of request:

    process file 1 and file 2 and add title as square and triangle
    process using column 1 and 3 with lp

"file 1"/"file 2" are ordinal, newest-first (never literal filesystem
numbers, since there's no reliable way to know those) -- file 1 is always the
most recent capture, file 2 the next-most-recent. Titles match positionally.
Verbal gnuplot syntax maps directly onto real gnuplot: "column 1 and 3" ->
`using 1:3`, "with lp" -> `with linespoints` -- the same thing you'd type by
hand, just spoken.

New: `measurements.find_recent_csvs()`, `gnuplot_export.PlotSpec` +
`launch_gnuplot_multi()` (multi-file plotting, real gnuplot, all files
overlaid with correct per-file titles and colors). `launch_gnuplot()` (single
file) is now a thin wrapper over the multi-file version, so existing callers
are unaffected.

Verified end-to-end with two real captures: "file 1" correctly resolved to
the newest, "file 2" to the next-newest, titles correctly attributed to the
right file, real gnuplot script validated with the actual installed gnuplot
6.0 binary (both default per-channel plotting and the verbal column/style
override). Plain "process" (no extra params) confirmed unchanged -- full
backward compatibility.

## Verified before packaging (this round)
- 23 backend/process tests (4 new: exact user command parses correctly,
  verbal column/style parsing, full multi-file pipeline round-trip with
  correct file/title resolution, backward-compatible single-file behaviour)
  plus 18 GUI tests (2 new: PortAudio detection, rewritten to avoid a global
  import-hook crash found during development): 41 total, all pass.
- CLI regression: generate+capture -> generate+capture (second shape) ->
  multi-file process with the exact user command -> exit.

## Fix: "process file N" resolved to an unexpected file with no way to notice
A real user hit this directly: "process file 4" resolved (correctly, per
ordinal semantics -- file 1 = newest, file 2 = next-newest, etc.) to an
OLDER capture than they'd just made, taken on a different channel. That part
was working as designed, but the response gave no way to catch the mismatch:
when a title was given, it fully REPLACED the real filename in the output,
so there was no visible clue that "file 4" hadn't pointed where expected.

Two-part fix:
1. `_handle_process` now ALWAYS states the real, stable filename in the
   summary -- title or not -- e.g. "square [acquisition_004]: ..." instead of
   just "square: ...". A surprising ordinal resolution is now immediately
   visible instead of hidden behind a title that looked right.
2. Added a second, literal addressing mode: "process acquisition 12" /
   "process capture number 12" always resolves to that exact file regardless
   of what's captured since (unlike "file N", which is deliberately relative
   and shifts). New `measurements.find_csv_by_id()`, new intent param
   `process_capture_ids`. "file N" (ordinal) remains the default -- it's the
   natural phrasing for "my last couple captures" -- literal IDs are there
   for when you already know the specific one you want.

Also fixed in the same pass: a single title ("process file 2, title it
square") wasn't recognized at all before -- the parser required at least two
titles joined by "and"/",". Now 1, 2, or 3 titles all parse correctly.

Verified by reproducing the exact reported scenario (four captures, the
newest on channel B, "file 4" resolving to an old channel-A capture) and
confirming the real filename is now visible in the response either way.

## Verified before packaging (this round)
- 26 backend/process tests (5 new: filename always visible with a title,
  single-title parsing, literal capture-ID stability across new captures,
  plus the two pre-existing suites) plus 18 GUI tests: 44 total, all pass.
- CLI regression: ordinal, titled-ordinal, and literal-ID addressing all
  produce correct, filename-transparent output.

## New: Vosk as an automatic offline speech-recognition fallback
PocketSphinx has repeatedly proven fragile in practice across this project's
real-hardware testing -- a mode-string comparison bug, a model directory-
layout mismatch, and a missing-PortAudio detection gap were each found and
fixed in turn, and it remained hard to get reliably working. Rather than
chase a fourth PocketSphinx-specific issue, a genuine second engine has been
added: `stt.py` now tries PocketSphinx first, and automatically falls back to
Vosk (prebuilt wheels, no compilation, no acoustic-model directory
fragility) if PocketSphinx is unavailable for any reason. Both are declared
in `requirements.txt`, so `setup.sh` installs both either way -- the only
manual step is downloading Vosk's model data (not pip-installable), documented
exactly in the new `VOICE_SETUP.md`.

Verified: PocketSphinx still works exactly as before (no regression from the
refactor); PocketSphinx-unavailable correctly falls through to a Vosk attempt;
a missing Vosk model gives a specific download instruction; a corrupted Vosk
model gives a distinct "re-download it" message; when both engines fail, both
real reasons are reported together, not just the last one tried. `setup.sh`'s
voice diagnostic and the GUI's status badge both now report which engine is
actually active (e.g. "voice: mic (vosk) + speech ready").

Honest limitation: an actual live Vosk transcription could not be verified in
this sandbox -- the real model is hosted only at alphacephei.com, which is
outside this environment's network allowlist, and no microphone is available
here either. The full fallback mechanism, error reporting, and engine
selection logic are proven; live recognition accuracy needs confirming on
real hardware with the model downloaded per VOICE_SETUP.md.

## Rename: display name changed to "LLM Project"
Every user-visible string -- GUI window title, in-app title label, CLI
startup banner, spoken TTS greeting, gnuplot window titles, and the
`--help` description -- now reads "LLM Project" instead of "PicoWave
Assistant". The underlying Python package name (`picowave`) and all
`python -m picowave.gui` / `python -m picowave.main` commands are
deliberately UNCHANGED, since renaming those would break every run command
already documented and used across this project's setup, for a purely
cosmetic gain. If a full package/import-path rename is actually wanted, that
is a separate, larger, riskier change and should be requested explicitly.

## Verified before packaging (this round)
- 26 backend/process tests + 18 GUI tests: 44 total, all pass, no
  regressions from either the voice refactor or the rename.
- CLI regression: renamed banner displays correctly; full generate-and-
  capture + process workflow unaffected.
- Live-constructed window confirmed: title reads "LLM Project", voice badge
  correctly names the active engine, PocketSphinx correctly still chosen as
  primary when available.

## Fix: PocketSphinx grammar crashed voice input outright ("millivolts" bug)
Root cause, confirmed directly against the real bundled dictionary: four
literal words in `config/grammar.jsgf` -- "millivolts", "kilohertz",
"sawtooth", "timebase" -- were not present in PocketSphinx's bundled
`cmudict-en-us.dict`. A JSGF grammar referencing ANY word outside that
dictionary fails to COMPILE at all, not just fails to recognize that word --
which crashed the entire recognizer ("RuntimeError: Failed to initialize
PocketSphinx", from deep inside `fsg_search.c`) the instant Voice was used,
with the grammar having silently drifted out of sync with the dictionary as
the project's vocabulary grew across many earlier feature additions.

Given this was the fourth distinct real PocketSphinx failure mode found
across this project's development (mode-string mismatch, model-path nesting,
missing-PortAudio detection, now this), the fix is decisive rather than a
fifth narrow patch:

1. **Engine priority swapped: Vosk is now tried first**, PocketSphinx second.
   Vosk does open-vocabulary recognition from its own trained model rather
   than a hand-maintained grammar checked word-by-word against a fixed
   dictionary, so it does not have this specific failure mode by
   construction.
2. **`grammar.jsgf` rewritten**: every literal word verified against the real
   dictionary (72 spoken-word tokens checked programmatically, zero missing);
   the four broken words replaced with dictionary-safe equivalents ("volts"
   for "millivolts", "kilo hertz" for "kilohertz", "saw tooth" for
   "sawtooth", "time base" for "timebase"). Also expanded to cover
   vocabulary added since the grammar was last touched -- dual-channel
   ("both channels"), the combined generate-and-capture action, "process",
   and relative adjustments ("increase"/"decrease"/"double"/"half") -- none
   of which were voice-reachable before.
3. **Defense in depth, for any future word this misses**: PocketSphinx's
   grammar is now actually validated (a real `LiveSpeech` construction, not
   just a files-exist check) at startup, not discovered mid-use. If it ever
   fails to compile again, PocketSphinx automatically falls back to open
   dictation instead of failing entirely, and `_listen_pocketsphinx` retries
   once without the grammar if a `RuntimeError` somehow still occurs at
   listen-time.
4. Fixed a bug caught while building this: a clean fallback success (Vosk
   unavailable, PocketSphinx works fine) was incorrectly leaving Vosk's
   failure message in `init_error`, making a normal, working fallback look
   like an active error. Cleared on any fully clean success.

Verified: the real, complete grammar file constructs successfully via
`LiveSpeech` (the exact call the app makes) -- confirmed past the
`fsg_search.c` failure point, the only remaining failure in this sandbox
being an unrelated `PortAudioError` from having no real microphone hardware
here. Vosk-first ordering confirmed (PocketSphinx is not even attempted when
Vosk succeeds). Four new permanent regression tests, including one that
scans the actual shipped grammar file against the real dictionary on every
test run, so a future vocabulary addition reintroducing this exact bug class
is caught immediately rather than in the field.

## Verified before packaging (this round)
- 26 backend/process tests + 22 GUI tests (4 new: Vosk-first ordering,
  clean-success error clearing, full grammar dictionary-completeness scan,
  end-to-end grammar compilation against the real PocketSphinx dictionary):
  48 total, all pass.
- CLI regression: unaffected by the voice-engine changes.

## Fix: grammar too rigid for natural phrasing ("generate me a sine wave at 2000 Hz")
Even with every word dictionary-valid (previous fix), PocketSphinx's closed
grammar still rejected genuinely natural phrasing because the grammar's word
ORDER was too rigid: it only accepted frequency BEFORE the waveform shape
("generate a 2000 hertz sine wave"), with no "me", and no trailing "at X Hz"
clause at all. "Generate me a sine wave at 2000 Hz" -- completely reasonable
phrasing -- matched the grammar in neither position, surfacing as "Final
result does not match the grammar" (non-fatal, but effectively unusable).

`grammar.jsgf` rewritten so frequency is accepted BOTH before the shape and
trailing with "at" after it, and optional filler ("me", "the", "please",
"now") is accepted throughout wherever people naturally add it. All 77
spoken-word tokens in the updated grammar re-verified against the real
dictionary (zero missing); the file re-confirmed to compile cleanly via a
real `LiveSpeech` construction, the same call the app makes.

Also documented, as a separate and unrelated real issue raised alongside
this one: Bluetooth headset/earbuds microphones commonly don't work at all
while the OS Bluetooth profile is in A2DP (output-only) mode -- the mic
needs the HSP/HFP profile, which Linux doesn't always switch to
automatically. This is an OS/profile issue, not something any change to this
project's code can fix -- `VOICE_SETUP.md` now has the exact `pactl`/
`pavucontrol` steps to check and switch the profile, plus a standalone
mic-level test to confirm whether audio is reaching the app at all,
independent of which recognition engine is being used.

## Verified before packaging (this round)
- 26 backend/process tests + 22 GUI tests (unchanged in count -- this was a
  grammar-content fix, not a new code path): 48 total, all pass.
- Grammar re-verified: full dictionary scan (77 words, zero missing) and a
  real LiveSpeech compile test, both passing.
- CLI regression: unaffected.
