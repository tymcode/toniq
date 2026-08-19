---
name: ts-sysex
description: >-
  TS-10/TS-12 MIDI System Exclusive rules (manufacturer 00 0F, device 07,
  SYS-EX OFF/ON/OLD, dump types, SEND-PARAMS, DEVICE-ID, bank vs single).
  Use when encoding/decoding .syx, talking to the instrument, or designing
  the Toniq librarian/editor protocol. Do not invent byte maps.
---

# SysEx

Source of truth: [notes/sysex.md](../../../notes/sysex.md) and `docs/Ensoniq TS series MIDI SysEx specification.pdf`.

## Do not

- Invent parameter addresses or dump layouts not written in `notes/sysex.md` or the spec PDF.
- Send a single-program dump to a bank location or the reverse.
- Overwrite ROM BankSets.
- Assume 16-part MULTI; MULTI is 12 tracks. GM is a separate 16-channel mode.

## Do

- Honor `SYS-EX=ON` vs `OLD` (pre-2.0 files need OLD).
- Address SysEx with `DEVICE-ID`.
- For live edits, prefer documented parameter-change messages; if absent, throttled current-Program dump.
- Warn before overwriting a named user slot.
- Pause between bulk messages.
