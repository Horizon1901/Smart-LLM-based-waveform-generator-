# Developer Guide

## Module responsibilities

| Module | Responsibility |
| --- | --- |
| `config.py` | Dataclass defaults + optional `config.yaml` overlay |
| `logger.py` | App log + per-session JSONL event stream |
| `intent.py` | `Action` enum, `SessionState`, `Intent`, validation/clamp, enum maps |
| `llm/prompts.py` | Schema-only intent prompt; freeform C prompt |
| `llm/client.py` | `OllamaClient` (stdlib HTTP) + rule-based `MockLLM` |
| `codegen/generator.py` | Deterministic template assembly → `generated/*.c` |
| `codegen/freeform.py` | Opt-in LLM-writes-C path |
| `compiler/builder.py` | `gcc` wrapper, mock/real link, captured output |
| `executor/runner.py` | Run binary, capture stdout/stderr/exit, extract `RESULT:` |
| `backup/manager.py` | Snapshot before modify; last-good rollback |
| `pipeline.py` | Orchestrates all stages; retry/rollback loop |
| `main.py` | CLI, LLM selection, REPL / once / batch |

## The intent contract

The LLM (or `MockLLM`) returns exactly:

```json
{ "action": "acquire|siggen|arb|set_param|help|exit|unknown",
  "params": { ...only-specified-fields... },
  "confidence": 0.0,
  "notes": "" }
```

`params` keys must match `SessionState` field names. Unknown keys are ignored;
values are clamped in `SessionState.clamp()`.

## Add a new command in three steps

Example: add a **frequency sweep**.

1. **State** — add fields to `SessionState` (e.g. `sweep_stop_hz`, `sweep_type`)
   with defaults and clamps.
2. **Template** — add `templates/sweep.c.tmpl` (copy `siggen.c.tmpl`, replace the
   `ps2000_set_sig_gen_built_in` args with the sweep parameters — still a real
   manufacturer API call). Add a `_render_sweep` + a branch in
   `CodeGenerator.generate()`.
3. **Intent** — add `SWEEP = "sweep"` to `Action`, mention it in
   `INTENT_SYSTEM_PROMPT`, and (for offline testing) a rule in `MockLLM`.

No other module changes. The compile/run/log/backup machinery is action-agnostic.

## Templates

Placeholders are `{{TOKEN}}`; `CodeGenerator._fill` does literal substitution.
Keep every emitted call a real `ps2000_*` function that appears in the
manufacturer example. Each template must:

* include `<stdio.h>` and (Linux) `"libps2000/ps2000.h"`,
* provide `main()` that opens the unit, does the work, prints a `RESULT:` line,
  and closes the unit,
* be self-contained (no external files required at runtime).

## Testing

```bash
python tests/test_intent.py     # intent parsing + state clamp
python tests/test_codegen.py    # generation + compile against mock
# or, if pytest is installed:
pytest tests/
```

`test_codegen.py` compiles every action against the mock SDK — run it after any
template change. To prove real-SDK compatibility without hardware, keep the mock
header in sync with the manufacturer's usage (it already covers the full API
surface the templates use).

## Coding conventions

* Core orchestration stays dependency-free (stdlib only); voice/config extras are
  optional and degrade gracefully.
* Every externally-observable stage emits a `logger.event(...)`.
* Never overwrite a generated file; always allocate the next id.
* Clamp all device parameters before they reach a template.

## Freeform mode notes

`freeform.py` deliberately feeds only the manufacturer API surface, no worked
solution algorithms. Failures are expected and handled by the pipeline's
rollback/retry. Treat freeform output as untrusted: it is compiled in the same
sand---boxed gcc step and never executed unless it builds cleanly.
