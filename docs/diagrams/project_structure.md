# Project Structure Diagrams

## Directory tree

```mermaid
flowchart TD
    ROOT[picowave-assistant/]
    ROOT --> MAN[manufacturer/<br/>ps2000Con.c + linux-build-files<br/>UNTOUCHED base]
    ROOT --> TMPL[templates/<br/>acquire / siggen / arb .c.tmpl]
    ROOT --> GEN[generated/<br/>acquisition_NNN.c + .csv<br/>never overwritten]
    ROOT --> MOCK[mock/<br/>ps2000.h + ps2000_mock.c<br/>offline SDK shim]
    ROOT --> SRC[src/picowave/]
    ROOT --> CFG[config/<br/>config.yaml + grammar.jsgf]
    ROOT --> SCR[scripts/]
    ROOT --> DOC[docs/]
    ROOT --> TST[tests/]
    ROOT --> BUILD[build/ · logs/ · backup/<br/>runtime output]

    SRC --> S1[config.py · logger.py · intent.py]
    SRC --> S2[llm/ client.py · prompts.py]
    SRC --> S3[codegen/ generator.py · freeform.py]
    SRC --> S4[compiler/ builder.py]
    SRC --> S5[executor/ runner.py]
    SRC --> S6[voice/ stt.py · tts.py]
    SRC --> S7[backup/ manager.py]
    SRC --> S8[pipeline.py · main.py]
```

## Manufacturer → template → generated relationship

```mermaid
flowchart LR
    subgraph Base [manufacturer/ps2000Con.c  -- never edited]
        F1[collect_block_immediate]
        F2[collect_block_triggered]
        F3[set_sig_gen]
        F4[set_sig_gen_arb]
        F5[adc_to_mv / mv_to_adc]
    end

    F1 & F2 & F5 --> T1[templates/acquire.c.tmpl]
    F3 --> T2[templates/siggen.c.tmpl]
    F4 --> T3[templates/arb.c.tmpl]

    T1 --> G1[generated/acquisition_001.c]
    T2 --> G2[generated/acquisition_002.c]
    T3 --> G3[generated/acquisition_003.c]

    style Base fill:#eef,stroke:#88a
```

The templates reproduce the manufacturer's exact `ps2000_*` call sequences; the
generator only substitutes parameters (channel, range, trigger, timebase,
waveform, frequency, amplitude, offset). No manufacturer code is rewritten and no
new PicoSDK APIs are invented.
```
