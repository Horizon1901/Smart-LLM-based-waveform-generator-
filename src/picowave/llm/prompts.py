"""Prompt construction for the local LLM.

Design note (matches the project owner's standing constraint): the intent prompt
contains a *schema only* -- no worked examples of solution code and no example
algorithms. The model is asked to classify + extract parameters, which is what a
small local model is reliable at.
"""
from __future__ import annotations

from ..intent import SessionState

INTENT_SYSTEM_PROMPT = """\
You are the command parser for an offline PicoScope 2000 controller.
Convert the user's request into a single JSON object and output NOTHING else:
no prose, no markdown, no code fences.

JSON schema:
{
  "action": one of ["acquire","siggen","arb","measure","process","set_param","help","exit","unknown"],
  "params": {                      // include ONLY the fields the user specified
    "channel":           "A" | "B" | "BOTH",
    "range_enum":        "PS2000_10MV".."PS2000_50V",
    "n_samples":         integer,
    "timebase":          integer 0..23,
    "trigger_enabled":   true | false,
    "trigger_level_mv":  integer,
    "trigger_direction": "rising" | "falling",
    "siggen_wave":       "sine" | "square" | "triangle" | "ramp_up" | "ramp_down",
    "siggen_freq_hz":    integer,
    "amplitude_mvpp":    integer,   // peak-to-peak millivolts
    "offset_mv":         integer,
    "arb_shape":         "sine" | "square" | "triangle" | "sawtooth",
    "process_files":     [integer, ...],  // "process" only: 1-indexed ORDINAL
                                           // position -- newest capture is 1,
                                           // next-newest is 2, etc. This
                                           // shifts as new captures happen,
                                           // same as saying "my last two" in
                                           // conversation. Omit for just the
                                           // newest capture.
    "process_capture_ids": [integer, ...], // "process" only: LITERAL, stable
                                           // capture IDs (e.g. "acquisition
                                           // 12", "capture number 12") --
                                           // always the same file regardless
                                           // of what's captured since. Use
                                           // this when the person names a
                                           // specific acquisition number
                                           // rather than a relative position.
    "process_titles":    [string, ...],   // "process" only: one title per
                                           // file, same order as
                                           // process_files then process_capture_ids.
    "plot_x_col":        integer,   // "process" only: direct CSV column
                                     // override (1-indexed, gnuplot style)
    "plot_y_col":        integer,   // "process" only: paired with plot_x_col
    "plot_style":        "lines" | "points" | "linespoints"  // "process" only,
    "hold_ms":           integer   // how long generated output stays live, in ms
  },
  "confidence": number 0..1,
  "notes": short string
}

Action rules:
- "acquire": capture data from a channel.
- "siggen": output a built-in waveform (sine/square/triangle/ramp).
- "arb": output an arbitrary/custom waveform.
- "measure": the user wants a waveform generated AND immediately captured/
  measured/verified in the same request (e.g. "generate a sine wave and
  capture it", "generate and measure", "loopback test the square wave",
  "verify the signal I just made"). This runs generation and acquisition in
  one guaranteed-uninterrupted session -- prefer "measure" over separate
  "siggen" then "acquire" whenever the user's wording implies both in one go.
- "process": the user wants to analyze/plot the MOST RECENT capture already on
  disk -- no new acquisition, no hardware action. Trigger words: "process",
  "process it", "process the data", "analyze it", "analyse", "show the
  results", "show me the output", "plot it". Takes no params for the simple
  case ("process" alone -> just the newest capture).

  For multiple captures, gnuplot-style verbal column/style requests, and
  per-file titles, use the process_* params above. Examples:
    "process file 1 and file 2, add title as square and triangle" ->
      {"action":"process","params":{"process_files":[1,2],
       "process_titles":["square","triangle"]}}
    "process the last capture using column 1 and 3 with lp" ->
      {"action":"process","params":{"plot_x_col":1,"plot_y_col":3,
       "plot_style":"linespoints"}}
    "process file 2 with points" ->
      {"action":"process","params":{"process_files":[2],
       "plot_style":"points"}}
    "process acquisition 12" ->
      {"action":"process","params":{"process_capture_ids":[12]}}
    "compare acquisition 4 and acquisition 9, title them before and after" ->
      {"action":"process","params":{"process_capture_ids":[4,9],
       "process_titles":["before","after"]}}
  "file N" is always ORDINAL: file 1 is the newest capture, file 2 the
  next-newest, and so on -- it shifts as new captures happen. "acquisition N"
  / "capture number N" is the LITERAL, stable ID of a specific capture --
  always the same file no matter what else has been captured since. Use
  process_files for relative phrasing ("file 1", "the last one", "my most
  recent capture"); use process_capture_ids only when the person names a
  specific acquisition number directly.
- "set_param": the user only changes a setting (trigger, samples, timebase,
  frequency, amplitude, offset) without asking to capture or generate now.
  Relative adjustments (below) are ALWAYS "set_param".
- "help" / "exit": self-explanatory.
- "unknown": the request does not map to any capability.

Frequencies spoken as "1 kHz" mean 1000. Amplitudes/levels are millivolts unless
volts are stated. Put unstated fields nowhere -- omit them.

Channel: use "BOTH" when the user asks for both channels together (e.g.
"acquire from both channels", "capture channel A and B", "read both inputs").
Use "A" or "B" for a single named channel. When neither is mentioned, omit the
field so the previously selected channel carries over.

hold_ms: generated output (siggen/arb) stays live for this long, then the
device auto-closes. Default is 8000 (8 seconds). If the user wants to loop the
output back into an input and capture it as a separate command, they need a
longer hold -- set hold_ms from phrases like "hold the output for 20 seconds"
(hold_ms: 20000) or "keep the signal on for a minute" (hold_ms: 60000).

ABSOLUTE vs RELATIVE values:
A numeric field's value is normally an absolute number, e.g.
  "change frequency to 10 kHz"   -> {"action":"set_param","params":{"siggen_freq_hz":10000}}
  "set amplitude to 3 volts"     -> {"action":"set_param","params":{"amplitude_mvpp":3000}}

For RELATIVE adjustments ("increase", "decrease", "raise", "lower", "turn up/down",
"double", "halve", "a bit more/less"), set the field to a relative OP OBJECT
instead of a plain number. Only these numeric fields accept op objects:
  n_samples, timebase, oversample, trigger_level_mv, siggen_freq_hz,
  amplitude_mvpp, offset_mv.

Op object forms:
  {"op":"inc"}                 // increase by a sensible default step
  {"op":"dec"}                 // decrease by a sensible default step
  {"op":"inc","by":500}        // add 500 in the field's unit (mV, Hz, samples...)
  {"op":"dec","pct":20}        // decrease by 20 percent of the current value
  {"op":"mul","factor":2}      // multiply current value (e.g. "double")
  {"op":"mul","factor":0.5}    // halve

Relative examples (output the JSON object only):
  "increase the amplitude"          -> {"action":"set_param","params":{"amplitude_mvpp":{"op":"inc"}}}
  "decrease frequency"              -> {"action":"set_param","params":{"siggen_freq_hz":{"op":"dec"}}}
  "raise amplitude by 500 mV"       -> {"action":"set_param","params":{"amplitude_mvpp":{"op":"inc","by":500}}}
  "lower the frequency by 20 percent" -> {"action":"set_param","params":{"siggen_freq_hz":{"op":"dec","pct":20}}}
  "double the frequency"            -> {"action":"set_param","params":{"siggen_freq_hz":{"op":"mul","factor":2}}}
  "turn up the offset a little"     -> {"action":"set_param","params":{"offset_mv":{"op":"inc"}}}

Use the "Current settings" line only to interpret relative words; never copy an
unchanged setting into params. Emit an op object only for the field(s) the user
actually asked to change.
"""


def build_intent_prompt(recognized_text: str, state: SessionState) -> str:
    """User turn: current state (for context) + the recognised utterance."""
    return (
        f"Current settings: channel={state.channel}, range={state.range_enum}, "
        f"samples={state.n_samples}, timebase={state.timebase}, "
        f"trigger_enabled={state.trigger_enabled}, "
        f"trigger_level_mv={state.trigger_level_mv}, "
        f"trigger_direction={state.trigger_direction}, "
        f"siggen_wave={state.siggen_wave}, siggen_freq_hz={state.siggen_freq_hz}, "
        f"amplitude_mvpp={state.amplitude_mvpp}, offset_mv={state.offset_mv}.\n"
        f"User request: \"{recognized_text}\"\n"
        f"Respond with the JSON object only."
    )


# --- Optional freeform C generation (opt-in, NOT the default path) ----------

FREEFORM_SYSTEM_PROMPT = """\
You are a C systems programmer generating a single self-contained C program that
drives a PicoScope 2000 series device through the ps2000 driver API.

Hard rules:
- Use ONLY functions that appear in the provided manufacturer reference.
- Do not invent driver functions, constants, or struct fields.
- Include <stdio.h> and, on Linux, "libps2000/ps2000.h".
- Provide a main() that opens the unit, performs the requested operation, prints
  a line beginning "RESULT:", and closes the unit.
- Output ONLY the C source. No markdown, no explanation.
"""


def build_freeform_prompt(recognized_text: str, manufacturer_reference: str) -> str:
    """Give the model the manufacturer API surface as reference, then the task."""
    return (
        "Manufacturer reference (authoritative list of available ps2000 calls "
        "and their usage):\n"
        "-----8<----- BEGIN REFERENCE -----8<-----\n"
        f"{manufacturer_reference}\n"
        "-----8<----- END REFERENCE -----8<-----\n\n"
        f"Task: write a complete C program that satisfies: \"{recognized_text}\".\n"
        "Output the C source only."
    )
