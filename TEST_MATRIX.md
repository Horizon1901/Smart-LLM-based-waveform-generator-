# PicoWave Assistant — Complete Test Matrix

Work through this top to bottom. Each section is independent, so skip ahead if
something doesn't apply to your setup. Check the **console panel** after every
command — it shows `[intent]`, `[state]`, `[compile]`, `[execute]` lines that
confirm what actually happened, not just what was spoken back.

---

## 0. Environment sanity (always first)

```
source venv/bin/activate
which python3                     # must end in venv/bin/python3
./setup.sh                        # re-run any time; safe, idempotent
```
Check `setup.sh`'s final output for: gcc/espeak-ng/libps2000/libportaudio2
found, python imports OK, and the live voice diagnostic result.

```
PYTHONPATH=src python3 -m pytest tests/ -v
```
**Expected: 41 passing.** This alone confirms every piece below is
*structurally* sound before you spend time on manual GUI testing.

---

## 1. First launch — mock mode (zero risk, no hardware/model)

```
PYTHONPATH=src python3 -m picowave.gui --sdk mock --llm mock
```
- [ ] Window opens, three tabs visible (Result / Generated C / CSV viewer)
- [ ] Badges show: SDK: mock, LLM: mock, a voice status badge
- [ ] Console panel is empty until the first command runs

---

## 2. Signal generation (siggen)

```
Generate a sine wave at 1000 Hz
Generate a square wave at 2000 Hz
Generate a triangle wave at 1500 Hz
Generate a ramp up at 500 Hz
Generate a ramp down at 500 Hz
```
- [ ] Result tab plots an ideal waveform matching the requested shape
- [ ] 1000 Hz vs 2000 Hz visibly differ in cycle density (not just axis labels)
- [ ] Generated C tab shows real source calling `ps2000_set_sig_gen_built_in`

```
Set amplitude to 3 volts
Set offset to 200 mV
Generate a sine wave
```
- [ ] Plot reflects the new amplitude/offset without restating them

---

## 3. Acquisition (single + dual channel)

```
Acquire 1024 samples from channel A
Acquire 4096 samples from channel A
Acquire from channel B
Acquire from both channels
Acquire 8000 samples from both channels
```
- [ ] Each produces a real CSV in `generated/`
- [ ] Dual-channel: both `chA_mv` and `chB_mv` columns populate when wired
- [ ] 8000-sample dual request auto-caps (~4000) and still succeeds, no hang

```
Acquire 16 samples from channel A
Acquire 32000 samples from channel A
```
- [ ] Floor (16) succeeds with a tiny capture
- [ ] Ceiling clamps to 32000, then fails cleanly with a specific "doesn't fit
      in one block" message — not a hang, not a generic error

---

## 4. Range, timebase, trigger

```
Set channel A range to 1 V
Acquire 1024 samples from channel A
Set channel A range to 5 V
Acquire 1024 samples from channel A
```
- [ ] Same physical signal looks different in scale between the two ranges

```
Set timebase to 5
Acquire 1024 samples from channel A
Set timebase to 15
Acquire 1024 samples from channel A
```
- [ ] Higher timebase spans a visibly longer time window for the same sample count

```
Set trigger level to 300 mV
Enable rising trigger
Acquire 1024 samples from channel A
Set trigger level to -300 mV
Enable falling trigger
Acquire 1024 samples from channel A
```
- [ ] Console shows the trigger config reflected in generated C each time

---

## 5. Generate + capture (the race-condition fix — critical path)

With a loopback wire connected to Channel A:
```
Generate a sine wave at 2000 Hz and capture it
```
- [ ] Result/CSV tabs show a REAL waveform, not noise (this used to be
      impossible with separate generate/acquire commands)

```
Generate a square wave and capture both channels
```
- [ ] Both channels show real data if both are wired

```
Loopback test a 5 kHz sine wave
Verify the signal I just made
Make a triangle wave and check what it looks like on channel A
```
- [ ] All three phrasings correctly route to the combined action (check
      console `[intent] action=measure`), not separate siggen+acquire

---

## 6. Disconnected-input hint

```
Acquire 1024 samples from channel B
```
with nothing wired to B:
- [ ] Caption turns warning-colored: "looks flat/near-zero... check connection"

Then wire it and re-run:
- [ ] Warning disappears, real waveform shows

---

## 7. Waveform classification

```
Generate a sine wave at 2000 Hz and capture it
Process
```
- [ ] Says "looks like a sine wave (XX% match)"

Repeat for square and triangle — each should self-identify correctly.

```
Generate a triangle wave at 60 Hz and capture it
Process
```
- [ ] Very low frequency still classifies correctly (edge case)

Acquire from a disconnected/noisy channel, then `Process`:
- [ ] Says "does not clearly match sine, square, or triangle" — honest
      rejection, not a forced guess

---

## 8. Multi-file process + verbal gnuplot control

```
Generate a square wave at 1000 Hz and capture it
Generate a triangle wave at 1500 Hz and capture it
Process file 1 and file 2 and add title as square and triangle
```
- [ ] Real gnuplot window opens with BOTH curves, correctly labeled
- [ ] Spoken summary covers both files
- [ ] Generated C / CSV tabs show file 1 (the newest)

```
Generate a sine wave at 500 Hz and capture it
Process file 1 and file 2 and file 3, title them sine, square, triangle
```
- [ ] All three files plot together with correct labels (never tested beyond two before)

```
Process using column 1 and 3 with lp
Process file 1 with points
Process using columns 2 and 4
```
- [ ] Gnuplot window uses the exact columns/style requested each time

```
Process file 5
```
(when fewer than 5 captures exist)
- [ ] Clear "only N captures available" message — no crash

```
Process
Process file 1
```
- [ ] Both behave identically (file 1 = default = newest)

---

## 9. Relative / natural-language commands

```
Generate a sine wave at 1000 Hz
Increase the amplitude
Decrease frequency by 20 percent
Double the frequency
Raise the offset a little
```
- [ ] Plot updates live after EACH command — no need to re-run generate
- [ ] Spoken response reflects the new value each time

---

## 10. Settings persistence

```
(run any real-mode command, then close the app entirely)
PYTHONPATH=src python3 -m picowave.gui
```
- [ ] SDK/LLM badges show your last-used mode without re-specifying flags
- [ ] Session state (last frequency, channel, etc.) carries over

Explicit override test:
```
PYTHONPATH=src python3 -m picowave.gui --sdk mock --llm mock
(close it)
PYTHONPATH=src python3 -m picowave.gui --sdk real --llm ollama
```
- [ ] Badge shows "real" — an explicit flag must always win over a saved value

---

## 11. Voice input (needs PocketSphinx + mic + PortAudio)

```
./setup.sh
```
- [ ] Voice diagnostic line reports status clearly (ready, or a specific reason why not)

In the app:
- [ ] Status badge matches what setup.sh reported
- [ ] Click Voice, say nothing for 15+ seconds → "No speech detected, try
      again" (not stuck on "Listening...")
- [ ] Click Voice, speak a real command clearly → recognized and executed
- [ ] Try speaking one of the longer multi-file commands, not just a short one

---

## 12. Error handling / device conflicts (real hardware only)

Open the PicoScope desktop app first (claiming the device), then in this app:
```
Acquire 1024 samples from channel A
```
- [ ] Clear "device could not be opened" message, not a hang

Close the PicoScope app, retry — should now succeed.

---

## 13. Settings dialog (mid-session)

Menu → Settings → switch LLM to "mock" → OK
```
(run any command)
```
- [ ] Uses the rule-based parser instantly, no Ollama call

Switch back to "ollama" the same way:
- [ ] Real model resumes without restarting the app

---

## 14. CLI (not just GUI)

```
PYTHONPATH=src python3 -m picowave.main --text --sdk mock --llm mock
```
- [ ] All the same commands work identically from the terminal
- [ ] `help` lists the current command set including `process`
- [ ] `exit` shuts down cleanly

---

## 15. Housekeeping

```
ls generated/*.csv | wc -l
```
- [ ] Stays roughly bounded (~50) after heavy use, not growing forever

```
cat logs/session-*.jsonl | tail -5
```
- [ ] Structured JSONL events present for recent commands

---

## Priority if short on time

Sections **5** (race-condition fix), **7** (classification), and **8**
(multi-file process) are the newest, most complex, and least proven on real
hardware — start there. Section **10** (explicit-flag-override) is the one
that broke silently before, worth re-confirming. Everything else is stable
and lower-risk.

Report back with the exact command + console output for anything that
doesn't match what's checked above.
