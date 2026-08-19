---
name: ts-instrument-model
description: >-
  Enforces ENSONIQ TS-10/TS-12 object hierarchy and terminology (Program/Sound,
  Voice, Track, Preset, Sequence, Song, Sampled Sound, Hyper-Wave, BankSet).
  Use when editing Toniq code or docs, naming parameters, designing editor UI,
  or deciding how patches, tracks, or samples relate.
---

# TS instrument model

Read [notes/instrument-model.md](../../../notes/instrument-model.md) and [notes/glossary.md](../../../notes/glossary.md) before inventing names or data structures.

## Rules

- A stored sound is a **Program** (panel: Sound), not a “patch.” **Patch Select** is the two buttons / four voice combinations.
- A **Preset** is three **Tracks** plus one effect. Track parameters are shared with the sequencer.
- **Sampled Sounds** use the EPS/ASR layer/WaveSample engine. Do not encode them as six-voice Programs.
- Hyper-Wave is a **Wave-List** (≤16 steps) with START-STEP / LOOPSTART / END and MOD-DESTINATION including TRAVELER and START+LOOP.
- Hardware has one edit/Compare buffer. Host multi-buffer UIs still send one armed document to the device.
- TS-10 vs TS-12: keybed and aftertouch only; same SysEx and OS.

Spell Hyper-Wave, TransWave, Wave-List, WaveSample, BankSet, Poly-Key as in the glossary.
