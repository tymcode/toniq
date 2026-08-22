#!/usr/bin/env python3
"""Build structured HTML pages from the Musician's Manual transcript."""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = ROOT / "notes/transcript/musicians-manual.txt"
TERMS_PATH = ROOT / "notes/terms.json"
VFD_SCREENS_PATH = ROOT / "notes/vfd-screens.json"
OUT = ROOT / "manual"
IMAGES = OUT / "images"

# Glyphs the 2×40 VFD can draw (EnsoniqVFD.otf). Lowercase cannot appear on the device.
VFD_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,:+-*/_()=* ")

# PDF page numbers are 1-based inclusive start, exclusive end.
# Files that share a printed section are collected as one range, then split at a
# heading (never a page number) so chapters do not start mid-sentence.
PAGES = {
    "tips.html": (4, 6),
    "preface.html": (6, 16),
    "01-controls.html": (31, 44),
    "02-system.html": (44, 54),
    "03-midi.html": (54, 61),
    "04-presets.html": (61, 71),
    "05-track-params.html": (71, 88),
    "06-effects-concepts.html": (88, 96),
    "08-programs.html": (166, 201),
    "10-sequencer.html": (240, 276),
    "13-storage.html": (336, 362),
    "14-sampled-sounds.html": (362, 384),
    "15-sampled-params.html": (384, 408),
    "appendix-midi.html": (408, 410),
}

# (page_start, page_end_exclusive, [(filename, heading_regex_or_None), ...])
# The first part has pattern None (everything before the next heading).
SPLIT_RANGES = [
    (
        96,
        166,
        [
            ("07-effects-00-21.html", None),
            ("07-effects-22-40.html", r"^Dual Effects$"),
            ("07-effects-41-59.html", r"^41\s"),
            ("07-effects-60-73.html", r"^60\s"),
        ],
    ),
    (
        201,
        240,
        [
            ("09-program-params-a.html", None),
            ("09-program-params-b.html", r"^Wave Page$"),
        ],
    ),
    (
        276,
        311,
        [
            ("11-seq-params-edit.html", None),
            ("11-seq-params-locate.html", r"^Locate Page$"),
        ],
    ),
    (
        311,
        336,
        [
            ("12-midi-applications.html", None),
            ("12-general-midi.html", r"^What is General MIDI"),
        ],
    ),
]

TITLES = {
    "index.html": "Table of Contents",
    "tips.html": "List of Tips",
    "preface.html": "Preface",
    "01-controls.html": "Section 1 — Controls & Basic Functions",
    "02-system.html": "Section 2 — System Page Parameters",
    "03-midi.html": "Section 3 — MIDI Control Page Parameters",
    "04-presets.html": "Section 4 — Understanding Presets",
    "05-track-params.html": "Section 5 — Preset/Track Parameters",
    "06-effects-concepts.html": "Section 6 — Understanding Effects",
    "07-effects-00-21.html": "Section 7 — Effect Parameters (00–21 Parallel)",
    "07-effects-22-40.html": "Section 7 — Effect Parameters (22–40 Reverb)",
    "07-effects-41-59.html": "Section 7 — Effect Parameters (41–59 Delay/Mod)",
    "07-effects-60-73.html": "Section 7 — Effect Parameters (60–73 Amp/Filter)",
    "08-programs.html": "Section 8 — Understanding Programs",
    "09-program-params-a.html": "Section 9 — Program Parameters (LFO, Envelopes, Pitch, Filters)",
    "09-program-params-b.html": "Section 9 — Program Parameters (Wave, Hyper-Wave, Editors)",
    "10-sequencer.html": "Section 10 — Understanding the Sequencer",
    "11-seq-params-edit.html": "Section 11 — Sequencer Parameters (Edit)",
    "11-seq-params-locate.html": "Section 11 — Sequencer Parameters (Locate & Click)",
    "12-midi-applications.html": "Section 12 — Sequencing/MIDI Applications",
    "12-delay-tempo-chart.html": "Delay Times/Tempo BPM Chart",
    "12-general-midi.html": "Section 12 — General MIDI",
    "13-storage.html": "Section 13 — Storage",
    "14-sampled-sounds.html": "Section 14 — Understanding Sampled Sounds",
    "15-sampled-params.html": "Section 15 — Sampled Sound Parameters",
    "appendix-midi.html": "Appendix — MIDI Implementation",
    "search.html": "Search",
}

NAV_ORDER = [
    "index.html",
    "tips.html",
    "preface.html",
    "01-controls.html",
    "02-system.html",
    "03-midi.html",
    "04-presets.html",
    "05-track-params.html",
    "06-effects-concepts.html",
    "07-effects-00-21.html",
    "07-effects-22-40.html",
    "07-effects-41-59.html",
    "07-effects-60-73.html",
    "08-programs.html",
    "09-program-params-a.html",
    "09-program-params-b.html",
    "10-sequencer.html",
    "11-seq-params-edit.html",
    "11-seq-params-locate.html",
    "12-midi-applications.html",
    "12-delay-tempo-chart.html",
    "12-general-midi.html",
    "13-storage.html",
    "14-sampled-sounds.html",
    "15-sampled-params.html",
    "appendix-midi.html",
]

SECTION_LINE_RE = re.compile(r"^Section\s+(\d+)\s*[—–\-]\s*.+")


def section_anchor(title: str) -> str:
    """Stable id for a manual section title (title-block h1)."""
    m = re.match(r"Section\s+(\d+)\s*[—–\-]\s*(.+)", title.strip())
    if not m:
        return slugify(title)
    num, name = m.group(1), m.group(2)
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
    return f"section-{num}-{slug}"


def _norm_section_hint(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text).strip(" .,:;")
    return text.casefold()


def _section_files() -> dict[int, list[str]]:
    by_num: dict[int, list[str]] = {}
    for fname in NAV_ORDER:
        title = TITLES.get(fname, "")
        m = re.match(r"Section\s+(\d+)", title)
        if m:
            by_num.setdefault(int(m.group(1)), []).append(fname)
    return by_num


SECTION_FILES_BY_NUM = None  # filled in main()


def _load_section_files() -> dict[int, list[str]]:
    global SECTION_FILES_BY_NUM
    if SECTION_FILES_BY_NUM is None:
        SECTION_FILES_BY_NUM = _section_files()
    return SECTION_FILES_BY_NUM


SECTION_TITLE_ALIASES: dict[tuple[int, str], str] = {
    (1, "controls and basic functions"): "01-controls.html",
    (2, "system page parameters"): "02-system.html",
    (2, "system page"): "02-system.html",
    (3, "midi control page parameters"): "03-midi.html",
    (3, "midi control page"): "03-midi.html",
    (3, "midi control"): "03-midi.html",
    (4, "understanding presets"): "04-presets.html",
    (5, "preset/track parameters"): "05-track-params.html",
    (5, "preset/track"): "05-track-params.html",
    (6, "understanding effects"): "06-effects-concepts.html",
    (6, "effect concepts"): "06-effects-concepts.html",
    (7, "effect parameters"): "07-effects-00-21.html",
    (7, "effects parameters"): "07-effects-00-21.html",
    (8, "understanding programs"): "08-programs.html",
    (9, "program parameters"): "09-program-params-a.html",
    (10, "understanding the sequencer"): "10-sequencer.html",
    (11, "sequencer parameters"): "11-seq-params-edit.html",
    (12, "sequencing/midi applications"): "12-midi-applications.html",
    (12, "general midi"): "12-general-midi.html",
    (13, "storage"): "13-storage.html",
    (14, "understanding sampled sounds"): "14-sampled-sounds.html",
    (14, "understanding sampled"): "14-sampled-sounds.html",
    (15, "sampled sound parameters"): "15-sampled-params.html",
}


def resolve_section_target(num: int, hint: str = "") -> tuple[str, str]:
    """Return (filename, fragment id) for a section number and optional title hint."""
    hint_norm = _norm_section_hint(hint)
    if hint_norm:
        alias = SECTION_TITLE_ALIASES.get((num, hint_norm))
        if alias:
            return alias, section_anchor(TITLES[alias])
        for fname in _load_section_files().get(num, []):
            title_part = TITLES[fname].split(" — ", 1)[-1]
            tp_norm = _norm_section_hint(title_part)
            if hint_norm.startswith(tp_norm) or tp_norm.startswith(hint_norm):
                return fname, section_anchor(TITLES[fname])
            if len(hint_norm) >= 8 and (hint_norm in tp_norm or tp_norm in hint_norm):
                return fname, section_anchor(TITLES[fname])
    files = _load_section_files().get(num, [])
    if files:
        fname = files[0]
        return fname, section_anchor(TITLES[fname])
    return "index.html", ""


def section_href(num: int, hint: str = "", current_file: str | None = None) -> str:
    fname, anchor = resolve_section_target(num, hint)
    path = f"{fname}#{anchor}" if anchor else fname
    if current_file and fname == current_file:
        return f"#{anchor}" if anchor else path
    return path


FIGURES = {
    "06-effects-concepts.html": [
        ("page-088.png", "Effects overview"),
    ],
    "appendix-midi.html": [
        ("page-409.png", "MIDI Implementation Chart"),
    ],
}

# Figures inserted after a matching transcript line; following OCR leftovers are dropped.
INLINE_FIGURES = [
    {
        "after": re.compile(r"^Rear Panel Connections$"),
        "skip_until": re.compile(r"^1\) MIDI Thru"),
        "src": "rear-panel.png",
        "alt": (
            "Rear panel jacks numbered 1–11: MIDI Thru, Out, In, "
            "Foot Switch 2 and 1, Pedal·CV, Aux Outputs, Main Outs, and Phones"
        ),
        "caption": "Rear panel connections.",
    },
    {
        "after": re.compile(r"When the SW-2 is connected"),
        "skip_until": re.compile(r"^There are four parameters on the System page"),
        "src": "foot-switches.png",
        "alt": (
            "SW-2 single pedal (acts as the right foot switch) beside "
            "SW-10 dual pedal (left and right independently programmable)"
        ),
        "caption": "SW-2 (single) vs. SW-10 (dual) foot switches.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"using the following controls:$"),
        "skip_until": re.compile(r"^1\) Volume Slider"),
        "src": "front-panel-controls.png",
        "alt": (
            "Front-panel controls numbered 1–7: Volume Slider, Data Entry "
            "controls, Mode buttons, BankSet, display, soft buttons, and Bank 0–9"
        ),
        "caption": "Front panel controls.",
    },
    {
        "after": re.compile(r"located to the left of the keyboard:$"),
        "skip_until": re.compile(r"^• PATCH SELECT BUTTONS"),
        "src": "performance-controllers.png",
        "alt": (
            "Left-hand controllers: Patch Select buttons, Pitch Bend wheel, "
            "and Modulation wheel"
        ),
        "caption": "Patch Select buttons, Pitch Bend wheel, and Modulation wheel.",
    },
    {
        "after": re.compile(r"^Using the BankSet Button$"),
        "skip_until": re.compile(r"^The BankSet button is used to scroll"),
        "src": "bankset-display.png",
        "alt": (
            "Sounds-mode bank page showing U0-2 BOUZOUKI; U and 0 are the "
            "BankSet type and location, 2 is the bank page"
        ),
        "caption": (
            "U0 is the BankSet type and location; 2 is the bank page. "
            "BOUZOUKI is the selected sound."
        ),
    },
    {
        "after": re.compile(r"Period, slash and star are only available"),
        "skip_until": re.compile(r"^When KBD-NAMING=OFF"),
        "src": "kbd-naming.png",
        "alt": (
            "Keyboard naming map: white keys 0–9 and A–Z; black keys repeat "
            "Cursor Left, Cursor Right, Space, Dash, and Plus each octave"
        ),
        "caption": (
            "White keys enter 0–9 and A–Z. Each octave of black keys is "
            "Cursor Left, Cursor Right, Space, Dash, and Plus."
        ),
    },
    {
        "after": re.compile(r"Press and hold any of the Bank buttons \(0-9\)"),
        "skip_until": re.compile(r"^• Once you.ve selected a BankSet"),
        "src": "preset-save-bankset-buttons.png",
        "alt": (
            "Hold the BankSet button and press a Bank 0–9 button: "
            "0–1 User RAM, 2–7 ROM, 8–9 Sampled Sound BankSets"
        ),
        "caption": (
            "Hold BankSet and press Bank 0–9 to choose a BankSet "
            "(User RAM, ROM, or Sampled Sound)."
        ),
    },
    {
        "after": re.compile(r"^Power$"),
        "skip_until": re.compile(r"^Insert the line cord"),
        "src": "power-inlet.png",
        "alt": (
            "Rear-panel detail: lightning-bolt warning, power switch (1), "
            "and IEC AC inlet (2)"
        ),
        "caption": "Power switch (1) and AC line receptacle (2).",
    },
    {
        "after": re.compile(r"check to see if they are polarized or non-polarized"),
        "skip_until": re.compile(r"Exercise caution when using extension cords"),
        "src": "polarized-plugs.png",
        "alt": "Two-prong polarized plug (wider neutral blade) beside a non-polarized plug",
        "caption": "Polarized vs. non-polarized two-prong plugs.",
    },
    {
        "after": re.compile(r"The following diagram shows how cascading"),
        "skip_until": re.compile(r"Fig\. 1 depicts"),
        "src": "ground-loops.png",
        "alt": (
            "FIG. 1: two 3-prong grounded systems chained with an unbalanced cable, "
            "forming a ground loop. FIG. 2: one 3-prong and one 2-prong system, no loop"
        ),
        "caption": "Ground loop when chaining 3-prong systems (FIG. 1) vs. no loop (FIG. 2).",
    },
    {
        "after": re.compile(r"be sure to pan the left mixer input fully left"),
        "skip_until": re.compile(r"^It is a good idea to make sure your audio system"),
        "src": "amplification.png",
        "alt": (
            "TS-10 Main Audio Outputs to mixer, amp, and speakers; Phones jack to headphones; "
            "AC Power to a wall outlet"
        ),
        "caption": "Connecting the TS-10 to a mixer, amp, speakers, and headphones.",
    },
    {
        "after": re.compile(r"It is important not to alter this carrier"),
        "skip_until": re.compile(r"^Floppy disks are a magnetic storage"),
        "src": "floppy-disks.png",
        "alt": (
            "3.5-inch DSHD disk with disk window and write-protect tab, "
            "and DSDD disk with no extra window"
        ),
        "caption": "Write-protect tab and high-density window on 3.5″ disks.",
    },
    {
        "after": re.compile(
            r"^The illustration below shows a typical wave of this category"
        ),
        "skip": re.compile(
            r"^(Negative modulation|Positive modulation|Start|Point)$"
            r"|Negative modulation\s{2,}Positive modulation"
        ),
        "src": "transwave-modulation.png",
        "alt": (
            "TransWave waveform with a marked start point; "
            "negative modulation moves left, positive modulation moves right"
        ),
        "caption": (
            "Typical TransWave with the index near 50. "
            "Negative modulation moves the start point left; positive modulation moves it right."
        ),
    },
    {
        "after": re.compile(
            r"The diagram below shows the 16 Shaper tracking curves"
        ),
        "skip_until": re.compile(
            r"^Some possible applications for shaping the response of SRC-2"
        ),
        "src": "shape-curves.png",
        "alt": (
            "Sixteen Mod Mixer SHAPE tracking curves in a four-by-four grid: "
            "QUIKRISE, CONVEX-1 through CONVEX-3, LINEAR, CONCAVE1 through CONCAVE4, "
            "LATERISE, QUANT-32 through QUANT-02, and SMOOTHER"
        ),
        "caption": "The 16 Shaper tracking curves.",
    },
    {
        "after": re.compile(
            r"^Some possible applications for shaping the response of SRC-2"
        ),
        "skip_until": re.compile(r"^Program Control Page$"),
        "src": "shape-applications.png",
        "alt": (
            "Six examples of SRC-2 through Scale Factor and SHAPE: "
            "Convex, Concave, Quant-08, Smoother, and Linear with x2 clipping"
        ),
        "caption": "Applications of SHAPE to an SRC-2 signal.",
    },
    {
        "after": re.compile(r"Internally, the Mixer/Shaper works like this"),
        "skip_until": re.compile(r"^There are four parameters"),
        "src": "mod-mixer-block.png",
        "alt": (
            "Mod Mixer/Shaper block: SRC-1 goes straight to the mixer; "
            "SRC-2 passes through Scale and Shape before summing"
        ),
        "caption": "Internal signal flow of the Mod Mixer/Shaper.",
    },
    {
        "after": re.compile(
            r"The diagram below illustrates the make-up of a TS-10 program"
        ),
        "skip_until": re.compile(r"^Understanding Voices and Polyphony"),
        "src": "program-structure.png",
        "alt": (
            "TS-10 program structure: Patch Select variations, six voices, "
            "destination bus, dynamic effects, Main and Aux outputs"
        ),
        "caption": "TS-10 program structure.",
    },
    {
        "after": re.compile(r"^Voice Programming\b"),
        "skip_until": re.compile(r"^TS-10 Voice Configuration"),
        "src": "voice-programming-pages.png",
        "alt": (
            "Programming-section buttons: LFO, Env 1–3, Pitch, Pitch Mods, "
            "Filters, Output, Wave, and Mod Mixer outlined as Voice Programming "
            "Pages; Program Control/Layer and Program Effects sit beside them"
        ),
        "caption": "Voice programming pages in the Programming section.",
    },
    {
        "after": re.compile(
            r"The diagram on the following page shows the configuration of one TS-10 voice"
        ),
        "skip_until": re.compile(r"^Modulators$"),
        "src": "voice-configuration.png",
        "alt": (
            "TS-10 voice configuration: oscillator, dual filters, amplifier, "
            "three envelopes, LFO, noise, and Mod Mixer"
        ),
        "caption": "Configuration of one TS-10 voice.",
    },
    {
        "after": re.compile(
            r"The illustration below shows an example of three tracks with overlapping key zones"
        ),
        "skip_until": re.compile(r"^In order to set a Key Zone"),
        "src": "key-zones.png",
        "alt": (
            "Keyboard with overlapping Cellos, Piano, and Flute key zones"
        ),
        "caption": "Three tracks with overlapping key zones.",
    },
    {
        "after": re.compile(
            r"SQUARE — this positive-only square wave is useful for producing in-tune trill effects"
        ),
        "skip_until": re.compile(r"^RESTART-MODE"),
        "src": "lfo-waveshapes.png",
        "alt": (
            "Seven LFO waveshapes: TRIANGLE, SINE, SINE/TRI, POS/SINE, "
            "POS/TRI, SAWTOOTH, and SQUARE"
        ),
        "caption": "LFO waveshapes.",
    },
    {
        "after": re.compile(r"Typically, the NOISE signal might look like this"),
        "skip_until": re.compile(r"^NOISE-RATE determines how frequently"),
        "src": "noise-rate.png",
        "alt": (
            "Stepped random NOISE modulator with a bracket marking Noise Rate"
        ),
        "caption": "Typical NOISE modulator signal.",
    },
    {
        "after": re.compile(
            r"The illustration below shows the make-up of a TS-10 envelope"
        ),
        "skip_until": re.compile(r"^Each envelope page consists"),
        "src": "envelope-stages.png",
        "alt": (
            "TS-10 envelope: ATTACK, DECAY 1–3, KEY HELD, and RELEASE "
            "with PEAK, BREAK1, BREAK2, and SUSTAIN levels"
        ),
        "caption": "Make-up of a TS-10 envelope.",
    },
    {
        "after": re.compile(
            r"For a sustaining wave, when the Envelope Mode is Normal"
        ),
        "skip_until": re.compile(
            r"For a sustaining wave, when the Envelope Mode is set to Finish"
        ),
        "src": "envelope-steal-normal.png",
        "alt": (
            "Looped voice in NORMAL mode: the voice is free when ENV3 reaches zero"
        ),
        "caption": "Sustaining wave, Envelope Mode = Normal.",
    },
    {
        "after": re.compile(
            r"For a sustaining wave, when the Envelope Mode is set to Finish"
        ),
        "skip_until": re.compile(r"^For unlooped, non-sustaining"),
        "src": "envelope-steal-finish.png",
        "alt": (
            "Looped voice in FINISH mode: the voice is released when ENV3 "
            "reaches zero even if the key is still down"
        ),
        "caption": "Sustaining wave, Envelope Mode = Finish.",
    },
    {
        "after": re.compile(r"^For unlooped, non-sustaining"),
        "skip_until": re.compile(r"^VEL-CURVE"),
        "src": "envelope-steal-perc.png",
        "alt": (
            "Unlooped percussion wave: the voice is free when the sample ends, "
            "regardless of envelope level"
        ),
        "caption": "Unlooped “percussion” wave.",
    },
    {
        "after": re.compile(
            r"Available values are: QUIKRISE, CONVEX-1, CONVEX-2, CONVEX-3, "
            r"LINEAR, CONCAVE1, CONCAVE2, CONCAVE3, CONCAVE4, and LATERISE"
        ),
        "skip_until": re.compile(r"^KBDTRK"),
        "src": "velocity-curves.png",
        "alt": (
            "Ten envelope velocity-response curves from QUIKRISE through LATERISE"
        ),
        "caption": "Envelope velocity-response curves.",
    },
    {
        "after": re.compile(
            r"(The diagrams below show a number of possible filter configurations"
            r"|The following diagrams show some possible filter configurations)"
        ),
        "skip_until": re.compile(r"^FILTER 1 Page$"),
        "src": "filter-configurations.png",
        "alt": (
            "Filter 1 plus Filter 2 response curves combining into 4-pole "
            "low-pass or bandpass shapes"
        ),
        "caption": "Possible filter configurations.",
    },
    {
        "after": re.compile(
            r"Intermediate values will scale the voice from full level to an intermediate level"
        ),
        "skip_until": re.compile(r"^Setting a Keyboard Zone"),
        "src": "output-kbd-scale.png",
        "alt": (
            "OUTPUT KBD-SCALE at +99 and −99 across MIDI keys 0–127, "
            "with the TS-10 keyboard range marked"
        ),
        "caption": "Keyboard scaling of voice volume.",
    },
    {
        "after": re.compile(
            r"the voice will play at the same volume throughout the zone"
        ),
        "skip_until": re.compile(r"^The next two parameters on the top line"),
        "src": "output-kbd-zone.png",
        "alt": (
            "KBD-SCALE=ZON: full volume only between the specified low and high keys"
        ),
        "caption": "Keyboard zone with KBD-SCALE=ZON.",
    },
    {
        "after": re.compile(
            r"The diagram below shows a common routing of the signals for each bus"
        ),
        "skip_until": re.compile(r"^PAN\b"),
        "src": "destination-bus.png",
        "alt": (
            "Voice volume and pan feeding DESTINATION-BUS FX1, FX2, DRY, or AUX "
            "to Main or Aux outputs"
        ),
        "caption": "Destination-bus signal routing.",
    },
    {
        "after": re.compile(r"^Single Function Effect Mixer$"),
        "skip_until": re.compile(r"^The above illustration shows"),
        "src": "single-function-effect-mixer.png",
        "alt": (
            "Single-function effect mixer: Voice Output pan/vol to Destination Bus "
            "(FX1, FX2, DRY, AUX); FX1 and FX2 each pass through Mix1 or Mix2 into "
            "Effect 1, then to Main Outputs; DRY and AUX go to Main and Aux outputs"
        ),
        "caption": "Single-function effect mixer.",
    },
    {
        "after": re.compile(r"^Multiple Function Effect Mixer$"),
        "skip_until": re.compile(
            r"^When the selected algorithm is a combined effect"
        ),
        "src": "multiple-function-effect-mixer.png",
        "alt": (
            "Multiple-function effect mixer: FX1 through Effect 1 and Mix1, FX2 through "
            "Mix2 into Effect 2; dry paths from Mix1, Mix2, and DRY bus to Main Outputs"
        ),
        "caption": "Multiple-function effect mixer.",
    },
    {
        "after": re.compile(r"^Parallel Effect Mixer$"),
        "skip_until": re.compile(
            r"^All of the parallel effect algorithms follow"
        ),
        "src": "parallel-effect-mixer.png",
        "alt": (
            "Parallel effect mixer: FX1 L/R to Effect A and Effect B with A-to-B and "
            "reverb sends; FX2 to reverb and dry mix; DRY and AUX to Main and Aux outputs"
        ),
        "caption": "Parallel effect mixer.",
    },
    {
        "after": re.compile(
            r"^Small Plate Reverb & Large Plate Reverb 1 Signal Routing$"
        ),
        "skip_until": re.compile(
            r"^These two plate reverb algorithms share exactly the same signal routing topology"
        ),
        "src": "plate-reverb-routing.png",
        "alt": (
            "Small Plate and Large Plate Reverb 1 signal routing: FX1 and FX2 left/right "
            "inputs through Diffuser and Definition (Decay Diffuser) with feedback, "
            "cross-mix, LPF, and Main Outputs L/R"
        ),
        "caption": "Small Plate and Large Plate Reverb 1 signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^HALL REVERB 2 Signal Routing$"),
        "skip_until": re.compile(
            r"^The signal enters a low pass filter and goes directly through the diffusers"
        ),
        "src": "hall-reverb-2-routing.png",
        "alt": (
            "HALL REVERB 2 signal routing: FX1 and FX2 left/right inputs through LPF, "
            "Diffuser, Echo Time taps, Definition (Decay Diffuser) with feedback, "
            "cross-mix, and Main Outputs L/R"
        ),
        "caption": "HALL REVERB 2 signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^Non Linear Reverb Signal Routing$"),
        "skip_until": re.compile(
            r"^The signal goes directly through a diffuser which smears the signal"
        ),
        "src": "nonlinear-reverb-routing.png",
        "alt": (
            "Non Linear Reverb signal routing: FX-1 and FX-2 left/right inputs through "
            "Diffuser, Echo Time taps, Density, cross-mix, LPF, and Main Outputs L/R"
        ),
        "caption": "Non Linear Reverb signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(
            r"^ENVELOPE LEVEL 1\s+ENVELOPE LEVEL 2\s+ENVELOPE LEVEL 9$"
        ),
        "skip_until": re.compile(r"^ENVELOPE LEVELS \(1 to 9\)"),
        "src": "nonlinear-envelope-levels.png",
        "alt": (
            "Envelope levels 1 through 9: signal level over time with tap points "
            "for ENVELOPE LEVEL 1, 2, and 9 across the density"
        ),
        "caption": "Envelope levels 1–9 across the Non Linear Reverb density.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^Gated Reverb with a High Retrigger Threshold"),
        "skip_until": re.compile(r"^Gated Reverb with a Low Retrigger Threshold"),
        "src": "gated-reverb-high.png",
        "alt": (
            "Gated reverb with high retrigger threshold: signal level over time with "
            "Trigger, Retrigger, Attack Time, Hold Time, and Release marked on the envelope"
        ),
        "caption": "Gated reverb with a high retrigger threshold.",
    },
    {
        "after": re.compile(r"^Gated Reverb with a Low Retrigger Threshold"),
        "skip_until": re.compile(r"^HF DAMPING\s+Range:"),
        "src": "gated-reverb-low.png",
        "alt": (
            "Gated reverb with low retrigger threshold: repeated signal crossings above "
            "Trigger and Retrigger stack overlapping Hold Time periods"
        ),
        "caption": "Gated reverb with a low retrigger threshold.",
    },
    {
        "after": re.compile(r"^EQ- -STEREO DELAYLFO Signal Routing$"),
        "skip_until": re.compile(
            r"^The EFFECT MIX FX-1 and FX-2 DELAYLFO parameters can be routed"
        ),
        "src": "eq-stereo-delaylfo.png",
        "alt": (
            "EQ-STEREO DELAYLFO signal routing: FX-1 and FX-2 left/right inputs through "
            "EQ Trim, EQ, Left/Right Delay with LFO modulation, Delay-Regen, Damping (LPF), "
            "Cross Regen, Delay Input R, Output Level R, and Main Outputs L/R"
        ),
        "caption": "EQ- -STEREO DELAYLFO signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^EIGHT VOICE CHORUS Signal Routing$"),
        "skip_until": re.compile(r"^CHORUS RATE\s+Range:"),
        "src": "eight-voice-chorus-routing.png",
        "alt": (
            "Eight Voice Chorus signal routing: FX-1 and FX-2 left/right inputs summed "
            "per channel through 4 Voice Chorus (with Chorus Regen) and Delay paths; "
            "Delay Regen cross-couples left and right delays; Main Outputs L/R"
        ),
        "caption": "Eight Voice Chorus signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^EQ- -CHORUS \+ EQ- -DDL Signal Routing$"),
        "skip_until": re.compile(
            r"^The signal enters a programmable EQ"
        ),
        "src": "eq-chorus-eq-ddl-routing.png",
        "alt": (
            "EQ- -CHORUS + EQ- -DDL signal routing: FX-1 and FX-2 left/right inputs through "
            "linked Input Level Trim and EQ; left path through Chorus (Delay) with Regen "
            "Control and Echo (Echo Level) to Main Output L; right path through Chorus with "
            "cross-feed from left regen to Main Output R"
        ),
        "caption": "EQ- -CHORUS + EQ- -DDL signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^EQ- -FLANGER \+ DELAY Signal Routing$"),
        "skip_until": re.compile(r"^In this algorithm the signal enters"),
        "src": "eq-flanger-delay-routing.png",
        "alt": (
            "EQ- -FLANGER + DELAY signal routing: FX-1 and FX-2 left/right inputs through "
            "linked Input Level Trim and EQ; left path through Flanger with Delay Feedback "
            "and Echo (Echo Level) to Main Output L; right path through Flanger with "
            "cross-feed from left delay to Main Output R"
        ),
        "caption": "EQ- -FLANGER + DELAY signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^PHASER \+ DELAY Signal Routing$"),
        "skip_until": re.compile(r"^PHASER CENTER\s+Range:"),
        "src": "phaser-delay-routing.png",
        "alt": (
            "PHASER + DELAY signal routing: FX-1 and FX-2 left/right inputs summed per "
            "channel through Phaser (LFO) with linked Phaser Regen; left path feeds Delay "
            "with Delay Regen feedback to left and cross-feed to Main Output R; "
            "Main Outputs L/R"
        ),
        "caption": "PHASER + DELAY signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^EQ- -TREMOLO \+ DELAY Signal Routing$"),
        "skip_until": re.compile(r"^The signal enters an input level trim"),
        "src": "eq-tremolo-delay-routing.png",
        "alt": (
            "EQ- -TREMOLO + DELAY signal routing: FX-1 left/right through linked Input "
            "Level Trim, EQ, and Tremolo; FX-2 summed with left path through Delay and "
            "Echo (Echo Level) to Main Output L; right tremolo direct to Main Output R "
            "with Regen cross-feed from delay"
        ),
        "caption": "EQ- -TREMOLO + DELAY signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^EQ- -VIBRATO \+ DELAY Signal Routing$"),
        "skip_until": re.compile(
            r"^The signal enters a programmable EQ"
        ),
        "src": "eq-vibrato-delay-routing.png",
        "alt": (
            "EQ- -VIBRATO + DELAY signal routing: FX-1 left/right through EQ Trim, EQ, "
            "and Vibrato; left path through Delay and Echo (Echo Level) to Main "
            "Output L; right vibrato direct to Main Output R with Delay Regen "
            "cross-feed"
        ),
        "caption": "EQ- -VIBRATO + DELAY signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(r"^FLNG- -CMP- -DIST \+ REV Signal Routing$"),
        "skip_until": re.compile(r"^COMPRESSOR THRESH\s+Range:"),
        "src": "flng-cmp-dist-rev-routing.png",
        "alt": (
            "FLNG- -CMP- -DIST + REV signal routing: DRY bypasses to Main Outputs; "
            "FX1 through Flange, Comp, Distort, and EQ to Bus1; FX2 to Bus2; both "
            "buses feed Reverb with Reverb-to-Compressor feedback; summed L/R "
            "Main Outputs"
        ),
        "caption": "FLNG- -CMP- -DIST + REV signal routing.",
        "keep_trigger": False,
    },
    {
        "after": re.compile(
            r"The XFADE-TIME adds time to the duration of both the current step and the next step"
        ),
        "skip_until": re.compile(r"^DEPTH\b"),
        "src": "xfade-time.svg",
        "alt": (
            "Two DUR boxes for Step 1 and Step 2 with an X-shaped overlap labeled XFADE-TIME"
        ),
        "caption": "XFADE-TIME adds overlap to both the current and next step.",
    },
    {
        "after": re.compile(
            r"Determines how many decibels \(dB0? below normal volume the two wave steps will meet"
        ),
        "skip_until": re.compile(r"^\*EXIT\*"),
        "src": "xfade-depth.svg",
        "alt": (
            "Cross-fade volume graph: DEPTH=0 dB at the top of the X, "
            "DEPTH=6 dB at the crossing"
        ),
        "caption": "DEPTH is how far below full volume the two steps meet.",
    },
]

BUTTONS = [
    "Seqs/Songs",
    "Replace Track Sound",
    "Track Effects",
    "Select Voice",
    "Write Program",
    "Program Effects",
    "BankSet",
    "Presets",
    "Sounds",
    "Compare",
    "Storage",
    "System",
]

RUNNING_PHRASES = re.compile(
    r"TS-10 Musician.?s Manual|Table of Contents(?:\s+-\s+\d+)?|"
    r"Section \d+\s+[—–-].+|List of Tips|\bPreface\b|\bAppendix\b",
    re.I,
)
PAGE_NUM_RE = re.compile(r"^[ivxIVX]+$|^\d{1,3}$|^[IVX]+$")
ALGO_RE = re.compile(r"^(\d{2})\s+([A-Z0-9].{2,40})$")
GATED_REVERB_DIAGRAM_RE = re.compile(
    r"^Gated Reverb with a (High|Low) Retrigger Threshold\b",
    re.I,
)
RANGE_RE = re.compile(
    r"^(.{1,48}?)\s{2,}Ranges?:\s*(.+)$"
)
# Parameter + algo-specific range (e.g. "Non Lin 1, 3 Range:", "D-1 (L and R) Ranges:").
NAMED_RANGE_PARAM_RE = re.compile(
    r"^(.{1,48}?)\s{2,}(.+\sRanges?:\s*.+)$"
)
# Prose that follows a range value on the same PDF line.
PROSE_AFTER_RANGE = re.compile(
    r"\s+(?=(?:Controls|Sets|The|This|When|Determines|Allows|Selects|Press|If|In|For|"
    r"On any|Higher|Increasing|Acts|Smears|Adjusts|We recommend|A setting|Experiment|"
    r"Preechoes|Pre-echoes|However|decay,)\b)",
    re.I,
)
# Split multiple algo-specific range clauses for one parameter.
NAMED_RANGE_CLAUSE_SPLIT = re.compile(
    r"\s+(?=(?:Non Lin\s+\d+(?:,\s*\d+)?|Large Plate\s+\d|Large Room|Wide Ambience|"
    r"Small Plate|Medium Room|Tight Ambience|Hall Reverb\s+\d|Song|Seq|"
    r"D-\d+\s+\(L and R\))\s+Ranges?:\s*)",
    re.I,
)
# Second-line range clauses that belong to the previous parameter heading.
SECONDARY_RANGE_LINE_RE = re.compile(
    r"^(?:Non Lin\s+\d+|Large Plate\s+\d|Large Room|Wide Ambience|Small Plate|"
    r"Medium Room|Tight Ambience|Hall Reverb\s+\d|Song|Seq|"
    r"D-\d+\s+\(L and R\))\s+Ranges?:",
    re.I,
)
NOT_HEADING_START = re.compile(
    r"^(Press |When |If |The |There |This |These |You |It |In |For |With |"
    r"To |After |Before |Once |Note|Here |Sets |Determines |Selects |Allows |"
    r"Controls |Lets |Changing |Whenever |Assign |General |First |Second |"
    r"Higher |Lower |Setting |Voices |Any |Both |Each |All |Use |Using |"
    r"See |Refer |TS-10 |TS-12 |List of |Table of )",
    re.I,
)
TIP_RE = re.compile(r"^Tip:\s*(.*)$", re.I)
VFD_EQ_RE = re.compile(r"[A-Z0-9*][A-Z0-9+\-/*]*=[A-Z0-9+\-/*().]+")
LCD_STAR_RE = re.compile(r"\*[A-Z0-9*][A-Z0-9+\-/*]*\*")
# Complete field strings as they appear on the 2×40 (not parameter names).
LCD_FIELDS = [
    "SEND/RECV", "SEND/----", "LOCAL-OFF", "VOICE-OFF", "----/RECV", "MIDI-OFF",
    "-MONO-",
    "KEYBOARD", "STRING-SOUND", "BRASS+HORNS", "WIND+REEDS", "VOCAL-SOUND",
    "BASS-SOUND", "DRUM-SOUND", "CYMBALS", "PERCUSSION", "TUNED-PERCUS",
    "SOUND-EFFECT", "WAVEFORM", "INHARMONIC", "TRANSWAVE", "WAVE-LIST",
    "DRUM-MAP", "WAVELIST", "PITCHTBL",
    "START-STEP", "LOOP-START", "END-STEP", "ENDSTEP", "START+LOOP",
    "TRAVELER", "START-MODSRC",
]
PAGE_TITLE_RE = re.compile(r"^[A-Z0-9*].{0,48}\sPages?$", re.I)
MID_PHRASE_END = re.compile(
    r"\b(?:the|a|an|to|of|in|or|and|for|with|by|from|as|that|which|when|will)$",
    re.I,
)
# Compact LCD-style names in 2-column setting/description tables (00 PATCH, DRUM-FX1).
TABLE_NAME_RE = re.compile(
    r"^(?:"
    r"[A-Z0-9*\-][A-Z0-9*+\-/*]{1,20}"
    r"(?:[ -][A-Z0-9*][A-Z0-9*+\-/*]{0,16}){0,2}"
    r"|[LCR*-]{4,10}"
    r"|<[^>]+>"
    r")$"
)
DEFN_ROW_SPLIT = re.compile(
    r"(?<!\w)([A-Z]{2,8}(?:-[A-Z]{2,6})?|\*[A-Z]+\*)\s+(?=[a-z])"
)

SLUG_COUNTS: dict[str, int] = {}
USED_IDS: set[str] = set()
# Effect algorithm cross-links (Section 7 pages). Built in main().
EFFECT_ALGO_INDEX: dict[str, tuple[str, str]] = {}
EFFECT_PARAM_NAMES: list[str] = []
# Printed TOC titles → heading level. Loaded in main() before classify/unwrap.
TOC_HEADINGS: dict[str, str] = {}
TOC_ORIGINALS: dict[str, str] = {}
TOC_TITLE_KEYS: list[str] = []
TOC_SKIP_RE = re.compile(
    r"^(List of Tips|Preface|Table of Contents|Appendix|Index|TS-10 Index|Section \d+)\b",
    re.I,
)
TOC_LEADER_RE = re.compile(
    r"^(?P<indent>\s*)(?P<title>\S.*?)\s*\.{2,}\s*(?P<page>[ivxIVX\d]*)\s*$"
)
HEADING_SMALL_WORDS = {
    "a", "an", "the", "of", "and", "or", "to", "in", "for", "with", "your",
    "from", "on", "at", "by", "as", "when", "into", "than", "more", "one",
}
# IDs reserved by the page shell (<article id="main">, skip link, etc.).
PAGE_SHELL_IDS = {"main"}


def slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    s = s[:70] or "section"
    n = SLUG_COUNTS.get(s, 0) + 1
    if s in PAGE_SHELL_IDS and n == 1:
        n = 2
    while True:
        slug = s if n == 1 else f"{s}-{n}"
        if slug not in USED_IDS:
            SLUG_COUNTS[s] = n
            USED_IDS.add(slug)
            return slug
        n += 1


def load_pages() -> list[str]:
    raw = TRANSCRIPT.read_text(errors="replace")
    pages = raw.split("\f")
    return pages


def norm_heading(s: str) -> str:
    s = s.replace("™", "").replace("®", "").replace("©", "")
    s = s.replace("—", "-").replace("–", "-")
    s = re.sub(r"\s+", " ", s).strip()
    s = s.rstrip(".:")
    return s.casefold()


def _add_toc_title(out: dict[str, str], title: str, indent: int) -> None:
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title or TOC_SKIP_RE.match(title):
        return
    if re.fullmatch(r"[.\s]+", title) or PAGE_NUM_RE.match(title):
        return
    key = norm_heading(title)
    if len(key) < 2:
        return
    kind = "h4" if indent >= 8 else "h3"
    prev = out.get(key)
    if prev == "h3":
        return
    out[key] = kind
    orig = TOC_ORIGINALS.get(key)
    if orig is None or (orig.isupper() and not title.isupper()):
        TOC_ORIGINALS[key] = title


def parse_toc_titles(pages: list[str]) -> dict[str, str]:
    """Titles from the printed Table of Contents, with h3/h4 from indent."""
    out: dict[str, str] = {}
    pending: tuple[int, str] | None = None

    def flush_pending() -> None:
        nonlocal pending
        if pending:
            _add_toc_title(out, pending[1], pending[0])
            pending = None

    for page in pages:
        sample = page[:900] + page[-250:]
        if "Table of Contents" not in sample:
            flush_pending()
            continue
        for raw in page.splitlines():
            ln = raw.rstrip()
            s = ln.strip()
            if not s or is_running_header(s):
                continue
            if PAGE_NUM_RE.match(s) or re.fullmatch(r"\.+", s):
                continue
            m = TOC_LEADER_RE.match(ln)
            if m:
                title = m.group("title").strip()
                indent = len(m.group("indent"))
                if pending:
                    title = f"{pending[1]} {title}"
                    indent = pending[0]
                    pending = None
                _add_toc_title(out, title, indent)
                continue
            indent = len(ln) - len(ln.lstrip())
            if pending:
                if s[:1].isupper() or s[:1].islower():
                    pending = (pending[0], f"{pending[1]} {s}")
                    continue
                flush_pending()
            if (
                indent >= 4
                and s[0].isupper()
                and "...." not in s
                and not s.endswith(".")
                and len(s) < 90
                and not TOC_SKIP_RE.match(s)
            ):
                pending = (indent, s)
        flush_pending()
    return out


def load_toc(pages: list[str]) -> None:
    global TOC_HEADINGS, TOC_TITLE_KEYS, TOC_ORIGINALS
    TOC_ORIGINALS = {}
    TOC_HEADINGS = parse_toc_titles(pages)
    TOC_TITLE_KEYS = sorted(TOC_HEADINGS, key=len, reverse=True)


def is_prose_heading(line: str) -> bool:
    """Title-case section title that is not a sentence (The Sounds, Selecting a Preset)."""
    s = line.strip()
    if not s or len(s) > 78:
        return False
    if s.endswith((".", ",", ";")) or s.startswith(("•", "(")):
        return False
    if "...." in s or RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return False
    if is_multicolumn(s) or VFD_EQ_RE.search(s):
        return False
    if re.match(r"^\d+\)\s", s):
        return False
    words = re.findall(r"[A-Za-z0-9']+", s)
    if not (2 <= len(words) <= 14):
        return False
    if not any(c.islower() for c in s) or "  " in s or "," in s:
        return False
    if not words[0][:1].isupper():
        return False
    for i, w in enumerate(words):
        if i > 0 and w.lower() in HEADING_SMALL_WORDS:
            continue
        if w[:1].islower():
            return False
        if not (w[:1].isupper() or w[:1].isdigit()):
            return False
    if re.search(r"\b(is|are|was|were|will|can|should|must|has|have)\b", s):
        return False
    if words[-1].lower() in HEADING_SMALL_WORDS:
        return False
    if re.search(r"\bRanges?\s*:", s):
        return False
    if "+" in s or "Routing" in s or s.rstrip().endswith("+"):
        return False
    if MID_PHRASE_END.search(s.rstrip()):
        return False
    return True


def toc_heading_kind(line: str) -> str | None:
    if not TOC_HEADINGS:
        return None
    s = line.strip()
    if not s or s.startswith("•"):
        return None
    if s[:1].islower():
        return None
    if s.endswith((".", ",", ";")):
        return None
    key = norm_heading(s)
    if key in TOC_HEADINGS:
        orig = TOC_ORIGINALS.get(key, "")
        token = orig.strip("!?").replace("™", "")
        if " " not in token and "-" not in token:
            if orig.isupper() and not s.isupper():
                return None
        return TOC_HEADINGS[key]
    for title in TOC_TITLE_KEYS:
        orig = TOC_ORIGINALS.get(title, "")
        token = orig.strip("!?").replace("™", "")
        if orig.isupper() and " " not in token:
            continue
        if len(title) < 4:
            continue
        if key.startswith(title + " ") and is_prose_heading(s):
            return TOC_HEADINGS[title]
    return None


def is_running_header(s: str) -> bool:
    t = RUNNING_PHRASES.sub("", s)
    return t.strip(" —–-\t") == ""


def clean_page(text: str, first: bool) -> list[str]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    out: list[str] = []
    for i, ln in enumerate(lines):
        s = ln.strip()
        if not s:
            out.append("")
            continue
        if is_running_header(s):
            continue
        if PAGE_NUM_RE.match(s) and i > len(lines) - 4:
            continue
        if PAGE_NUM_RE.match(s) and i < 2 and not first:
            continue
        out.append(ln)
    return out


def is_vfd_text(s: str) -> bool:
    """True if s could appear on the TS display (uppercase + VFD punctuation only)."""
    if not s:
        return True
    return all(c in VFD_ALLOWED for c in s) and not any(c.islower() for c in s)


def is_multicolumn(line: str) -> bool:
    if RANGE_RE.match(line) or re.search(r"\bRanges?:", line):
        return False
    parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
    return len(parts) >= 3 and all(len(p) < 42 for p in parts)


ENUM_HEADING_RE = re.compile(r"^(\d{1,2})\)\s+(\S.*)$")
DIAGRAM_HEADING_SKIP = {"ENSONIQ", "CVP-1"}


def is_enum_heading(line: str) -> bool:
    """Numbered jack/control labels (`1) MIDI Thru`), not procedure steps."""
    m = ENUM_HEADING_RE.match(line.strip())
    if not m:
        return False
    rest = m.group(2).strip()
    if rest.endswith((".", ",", ";", "?", "!")):
        return False
    if len(line) > 48:
        return False
    words = rest.split()
    if not (1 <= len(words) <= 8):
        return False
    if rest[:1].islower() or NOT_HEADING_START.match(rest):
        return False
    if any(w[:1].islower() for w in words):
        return False
    if re.search(
        r"\b(select|press|play|connect|create|check|record|define|send|when|each)\b",
        rest,
        re.I,
    ):
        return False
    return True


def is_bullet_param_heading(line: str) -> bool:
    """Printed `• LFO — Low Frequency Oscillator` / `• *OFF*` labels, not option bullets."""
    s = line.strip()
    m = re.match(r"^•\s+(.+)$", s)
    if not m or len(s) > 48 or s.endswith((".", ",", ";", "?", "!")):
        return False
    rest = m.group(1).strip()
    if "•" in rest:
        return False
    parts = re.split(r"\s+[—–]\s+", rest, maxsplit=1)
    name = parts[0].strip()
    if not re.match(r"^[A-Z*][A-Z0-9* +\-/(),]*$", name):
        return False
    if len(parts) == 2 and parts[1][:1].islower():
        return False
    return True


def is_param_heading(line: str) -> bool:
    if is_bullet_param_heading(line):
        return True
    if len(line) > 48 or line.endswith((".", ",", ";", "?", "!")):
        return False
    if line in DIAGRAM_HEADING_SKIP:
        return False
    if NOT_HEADING_START.match(line) or VFD_EQ_RE.search(line) or "...." in line:
        return False
    if line.endswith(":") or is_multicolumn(line) or line.startswith("•"):
        return False
    if line.startswith("(") and line.endswith(")"):
        return False
    words = line.split()
    if re.match(r"^[A-Z*][A-Z0-9* +\-/*()&]{0,47}$", line) and "  " not in line:
        return True
    if (
        2 <= len(words) <= 6
        and "  " not in line
        and all(w[0].isupper() or not w[0].isalnum() for w in words)
    ):
        return True
    return False


def is_flush_line(s: str) -> bool:
    """Standalone PDF lines must not be joined to neighbors."""
    if not s:
        return True
    if TIP_RE.match(s) or RANGE_RE.match(s):
        return True
    if ALGO_RE.match(s) and len(s) < 48:
        return True
    if is_multicolumn(s) or split_twocol_row(s) or PAGE_TITLE_RE.match(s):
        return True
    if numeric_lookup_cells(s) or numeric_header_cells(s) or is_yesno_row(s):
        return True
    if s.endswith("Parameters") or (s.startswith("Section ") and "—" in s):
        return True
    if s.endswith(":") and len(s) < 50 and s[:1].isupper():
        return True
    if is_param_heading(s) or toc_heading_kind(s) or is_prose_heading(s):
        return True
    if s.startswith("•") or re.match(r"^\d+\)\s", s):
        return True
    if re.match(r"^Cursor\s+Cursor\b", s):
        return True
    if re.match(r"^0 1 2 3 4 5 6 7 8 9 A B C", s):
        return True
    return False


def _is_continuation(s: str) -> bool:
    return s[:1].islower() or s.startswith(
        ("and ", "or ", "the ", "of ", "in ", "a ", "an ", "to ")
    )


IDENTICAL_PARAMS_STUB_RE = re.compile(
    r"^These parameters are identical to the previous ones\b",
    re.I,
)


def consume_identical_params_stub_run(lines: list[str], i: int) -> int | None:
    """Skip bare param h4s naming params already documented for FX2."""
    if classify(lines[i]) != "h4":
        return None
    j = i
    count = 0
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        if classify(s) != "h4":
            break
        k = j + 1
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k < len(lines) and classify(lines[k]) == "range":
            break
        count += 1
        j += 1
    if not count:
        return None
    while j < len(lines) and not lines[j].strip():
        j += 1
    if j >= len(lines) or not IDENTICAL_PARAMS_STUB_RE.match(lines[j].strip()):
        return None
    return j


def gated_reverb_diagram_title(line: str) -> str | None:
    m = GATED_REVERB_DIAGRAM_RE.match(line.strip())
    if not m:
        return None
    return f"Gated Reverb with a {m.group(1).title()} Retrigger Threshold"


def range_incomplete(rng: str) -> bool:
    """True when a Range: value was split by a PDF line wrap."""
    if not rng:
        return False
    if rng.count("(") > rng.count(")"):
        return True
    if MID_PHRASE_END.search(rng):
        return True
    last = rng.split()[-1]
    if re.search(r"(?<!-)[A-Z0-9]+-$", last):
        return True
    if re.search(r"(,$|\bor$|\band$|\bto$)", rng, re.I):
        return True
    return False


def is_param_range_name(name: str) -> bool:
    if NOT_HEADING_START.match(name) or toc_heading_kind(name):
        return False
    if is_param_heading(name):
        return True
    if len(name) > 48:
        return False
    if not re.match(r"^[A-Z0-9*][A-Z0-9 ()+\-/a-z]*$", name):
        return False
    letters = [c for c in name if c.isalpha()]
    if not letters:
        return False
    upper_ratio = sum(c.isupper() for c in letters) / len(letters)
    return upper_ratio >= 0.45


def match_named_range_param(line: str) -> re.Match[str] | None:
    s = line.strip()
    if RANGE_RE.match(s):
        return None
    m = NAMED_RANGE_PARAM_RE.match(s)
    if not m:
        return None
    name = m.group(1).strip()
    if not is_param_range_name(name):
        return None
    return m


def parse_range_line(line: str) -> tuple[str, str] | None:
    s = line.strip()
    m = RANGE_RE.match(s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m = match_named_range_param(s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None


def split_range_clause_and_desc(text: str) -> tuple[str, str | None]:
    text = re.sub(r"\s+", " ", text).strip()
    m = PROSE_AFTER_RANGE.search(text)
    if m:
        return text[: m.start()].strip(), text[m.start() :].strip()
    return text, None


def is_secondary_range_line(line: str) -> bool:
    s = line.strip()
    if SECONDARY_RANGE_LINE_RE.match(s):
        return True
    m = RANGE_RE.match(s)
    return bool(m and m.group(1).strip() in ("Song", "Seq"))


def parse_secondary_range_line(line: str) -> tuple[str, str | None]:
    s = line.strip()
    m = RANGE_RE.match(s)
    if m and m.group(1).strip() in ("Song", "Seq"):
        clause = f"{m.group(1).strip()}  Range: {m.group(2).strip()}"
        return split_range_clause_and_desc(clause)
    return split_range_clause_and_desc(s)


def range_join(prev: str, s: str) -> str | None:
    """Reattach a PDF-wrapped Range: continuation to the parameter heading."""
    m = RANGE_RE.match(prev)
    if not m or not s:
        return None
    if RANGE_RE.match(s) or s.startswith("•") or TIP_RE.match(s):
        return None
    if PAGE_TITLE_RE.match(s) or (s.startswith("Section ") and "—" in s):
        return None
    rng = m.group(2).strip()
    if re.match(r"^Held Range:", s, re.I):
        return f"{prev}  {s}"
    if not range_incomplete(rng):
        return None
    value_like = bool(
        re.fullmatch(r"[A-Z0-9*+\-/,() ]+", s)
        and len(s) <= 60
        and not re.search(r"\b(the|this|when|will|from|page)\b", s, re.I)
    )
    if is_param_heading(s) and not value_like:
        return None
    if (toc_heading_kind(s) or is_prose_heading(s)) and not value_like:
        return None
    if NOT_HEADING_START.match(s) and not _is_continuation(s):
        if not (rng.count("(") > rng.count(")") and s.endswith(")") and len(s) <= 80):
            return None
    last = rng.split()[-1]
    if re.search(r"(?<!-)[A-Z0-9]+-$", last) and re.match(r"^[A-Z0-9]", s):
        return prev + s
    return f"{prev} {s}"


def is_bullet_item(s: str) -> bool:
    if is_enum_heading(s) or is_bullet_param_heading(s):
        return False
    return s.startswith("•") or bool(re.match(r"^\d+\)\s", s))


VOICE_ROUTING_BULLET_RE = re.compile(
    r"^•\s+(?:Voices assigned to|The output of Effect)\b",
    re.I,
)


def is_voice_routing_bullet(s: str) -> bool:
    return bool(VOICE_ROUTING_BULLET_RE.match(s.strip()))


def tag_fx_bus_names(html_text: str) -> str:
    """Wrap bare FX1/FX2 in span.param without double-wrapping."""
    parts = re.split(r"(<[^>]+>)", html_text)
    depth = 0
    for i, part in enumerate(parts):
        if part.startswith("<"):
            if part.startswith("</"):
                depth = max(0, depth - 1)
            elif not part.endswith("/>") and not part.startswith("<!"):
                depth += 1
            continue
        if depth == 0:
            parts[i] = re.sub(
                r"\b(FX[12])\b",
                r'<span class="param">\1</span>',
                part,
            )
    return "".join(parts)


def render_voice_routing_block(
    bullets: list[str], terms: dict[str, list[str]], fname: str
) -> str:
    lines: list[str] = []
    for idx, bullet in enumerate(bullets):
        tagged = tag_fx_bus_names(
            apply_tags(bullet, terms, source_file=fname)
        )
        if idx == 0:
            lines.append(tagged)
        else:
            lines.append(f"<br>\n   {tagged}")
    return f"<p>{''.join(lines)}</p>"


def consume_voice_routing_block(
    lines: list[str],
    i: int,
    terms: dict[str, list[str]],
    fname: str,
) -> tuple[str | None, int]:
    s = lines[i].strip()
    if not is_voice_routing_bullet(s):
        return None, i
    bullets = [s]
    j = i + 1
    while j < len(lines):
        k = j
        while k < len(lines) and not lines[k].strip():
            k += 1
        if k >= len(lines):
            break
        nxt = lines[k].strip()
        if is_voice_routing_bullet(nxt):
            bullets.append(nxt)
            j = k + 1
            continue
        break
    if len(bullets) < 2:
        return None, i
    return render_voice_routing_block(bullets, terms, fname), j


def bullet_join(prev: str, s: str) -> str | None:
    """Keep a PDF-wrapped bullet as one paragraph; do not eat the next paragraph."""
    if not is_bullet_item(prev) or not s:
        return None
    if is_bullet_item(s) or RANGE_RE.match(s) or TIP_RE.match(s):
        return None
    if PAGE_TITLE_RE.match(s) or (s.startswith("Section ") and "—" in s):
        return None
    if is_param_heading(s):
        return None
    if re.search(r"[.!?]$", prev):
        return None
    last = prev.split()[-1]
    if re.search(r"(?<!-)[A-Z0-9*]+-$", last) and re.match(r"^[A-Z0-9]", s):
        return prev + s
    # Same bullet, wrapped: lowercase leftover, hanging comma, “will select”, etc.
    if _is_continuation(s) or prev.rstrip().endswith((",", ";", "—", "–")):
        return f"{prev} {s}"
    if MID_PHRASE_END.search(prev):
        return f"{prev} {s}"
    # New sentence after a finished bullet (option list, closed clause).
    if NOT_HEADING_START.match(s):
        return None
    return f"{prev} {s}"


def tip_join(prev: str, s: str) -> str | None:
    """Keep a PDF-wrapped Tip: as one aside; do not eat the next paragraph."""
    if not TIP_RE.match(prev) or not s:
        return None
    if TIP_RE.match(s) or RANGE_RE.match(s) or is_bullet_item(s):
        return None
    if PAGE_TITLE_RE.match(s) or (s.startswith("Section ") and "—" in s):
        return None
    if is_param_heading(s) or split_twocol_row(s):
        return None
    if s.lower().startswith(("note:", "important:")):
        return None
    if re.search(r"[.!?]$", prev):
        return None
    last = prev.split()[-1]
    if re.search(r"(?<!-)[A-Z0-9*]+-$", last) and re.match(r"^[A-Z0-9]", s):
        return prev + s
    if _is_continuation(s) or prev.rstrip().endswith((",", ";", "—", "–")):
        return f"{prev} {s}"
    if MID_PHRASE_END.search(prev):
        return f"{prev} {s}"
    if NOT_HEADING_START.match(s):
        return None
    return f"{prev} {s}"


def should_merge_dangling_prose(prev: str, nxt: str) -> bool:
    """Rejoin PDF wraps that stopped mid-phrase (Section 7 and elsewhere)."""
    if not prev or not nxt:
        return False
    if is_flush_line(nxt) or is_flush_line(prev):
        return False
    if re.search(r"[.!?]$", prev.rstrip()):
        return False
    if re.search(r"For a complete description of the(?: remaining)?$", prev, re.I):
        return True
    if prev.rstrip().endswith("+") and re.match(r"^[A-Z0-9]", nxt):
        return True
    if re.search(r"refer to the [A-Z0-9+\-/ ]+$", prev, re.I):
        return True
    if prev.rstrip().endswith("(on the") and re.match(r"^Output page", nxt, re.I):
        return True
    if _is_continuation(nxt):
        return True
    if MID_PHRASE_END.search(prev.rstrip()):
        return len(nxt) < 120
    return False


def merge_dangling_prose(paras: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(paras):
        p = paras[i]
        if not p:
            out.append(p)
            i += 1
            continue
        merged = p
        while i + 1 < len(paras) and paras[i + 1].strip():
            nxt = paras[i + 1].strip()
            if not should_merge_dangling_prose(merged, nxt):
                break
            glue = "" if merged.rstrip().endswith("+") else " "
            merged = merged.rstrip() + glue + nxt
            i += 1
        out.append(merged)
        i += 1
    return out


def norm_effect_algo_key(name: str) -> str:
    s = re.sub(r"\s+", " ", name.strip().upper())
    s = re.sub(r"- -", "- -", s)
    return s


def effect_algo_slug(num: str, name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", f"{num} {name}".lower()).strip("-")
    return s[:70] or "effect"


def build_effect_manual_catalog(pages: list[str]) -> None:
    """Index Section 7 algorithm headings and parameter names for cross-links."""
    global EFFECT_ALGO_INDEX, EFFECT_PARAM_NAMES
    index: dict[str, tuple[str, str]] = {}
    param_names: set[str] = set()
    for start, end, parts in SPLIT_RANGES:
        if not any(fname.startswith("07-effects-") for fname, _ in parts):
            continue
        lines = collect_range(pages, start, end)
        chunks = split_parts(lines, parts)
        for fname, chunk in chunks.items():
            if not fname.startswith("07-effects-"):
                continue
            for ln in chunk:
                s = ln.strip()
                m = ALGO_RE.match(s)
                if m and len(s) < 48:
                    num, name = m.group(1), m.group(2).strip()
                    slug = effect_algo_slug(num, name)
                    key = norm_effect_algo_key(name)
                    if key not in index:
                        index[key] = (fname, slug)
                    continue
                rm = RANGE_RE.match(s)
                if rm:
                    param_names.add(rm.group(1).strip())
                elif is_param_heading(s) and len(s) < 48:
                    param_names.add(s.strip())
    EFFECT_ALGO_INDEX = index
    EFFECT_PARAM_NAMES = sorted(param_names, key=len, reverse=True)


def lookup_effect_algo(name: str) -> tuple[str, str] | None:
    key = norm_effect_algo_key(name)
    hit = EFFECT_ALGO_INDEX.get(key)
    if hit:
        return hit
    compact = re.sub(r"\s+", "", key)
    for k, v in EFFECT_ALGO_INDEX.items():
        if re.sub(r"\s+", "", k) == compact:
            return v
    return None


EFFECT_ALGO_REF_RE = re.compile(
    r"(\brefer to the )([A-Z0-9+\-/ ]+?)( algorithm\b|\bparameters\b)",
    re.I,
)


def link_effect_algo_refs(escaped: str, source_file: str | None) -> str:
    if not source_file or not source_file.startswith("07-effects-") or not EFFECT_ALGO_INDEX:
        return escaped

    def repl(m: re.Match[str]) -> str:
        prefix, name, suffix = m.group(1), m.group(2).strip(), m.group(3)
        hit = lookup_effect_algo(name)
        if not hit:
            return m.group(0)
        fname, slug = hit
        href = f"{fname}#{slug}" if fname != source_file else f"#{slug}"
        return (
            f'{prefix}<a class="algo" href="{html.escape(href, quote=True)}">'
            f"{html.escape(name)}</a>{html.escape(suffix)}"
        )

    parts = re.split(r"(<[^>]+>)", escaped)
    for i, part in enumerate(parts):
        if part.startswith("<"):
            continue
        parts[i] = EFFECT_ALGO_REF_RE.sub(repl, part)
    return "".join(parts)


def table_row_join(prev: str, s: str) -> str | None:
    """Keep a wrapped description in the same 2-column row; do not glue the next row."""
    row = split_twocol_row(prev)
    if not row or not s:
        return None
    if split_twocol_row(s) or split_twocol_row(s, in_table=True):
        return None
    if not is_table_desc_wrap(s, row[1], row_follows=False):
        return None
    return f"{row[0]}  {row[1]} {s}"


def token_hyphen_join(prev: str, s: str) -> str | None:
    """Rejoin an Ensoniq token split after a hyphen (START- / STEP → START-STEP)."""
    if not prev or not s:
        return None
    last = prev.split()[-1]
    if re.search(r"(?<!-)[A-Z0-9*]+-$", last) and re.match(r"^[A-Z0-9]", s):
        return prev + s
    return None


def is_figure_label_row(line: str) -> bool:
    """Mixed-case multi-column labels left after the PDF dropped the VFD font."""
    s = line.strip()
    if not s:
        return True
    if RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return False
    if split_twocol_row(s):
        return False
    if numeric_lookup_cells(s) or numeric_header_cells(s):
        return False
    if s[:1].islower() or s.endswith((".", "?", "!")):
        return False
    parts = split_cols(s)
    if len(parts) < 2 or any(len(p) > 36 for p in parts):
        return False
    return any(c.islower() for c in s)


CHART_REF_PATTERNS = [
    (re.compile(r"the Envelope Times chart(?: below)?", re.I), "#envelope-times"),
    (re.compile(r"the LFO Frequencies chart(?: below)?", re.I), "#lfo-frequencies"),
    (
        re.compile(r"Delay Times/Tempo BPM Chart", re.I),
        "12-delay-tempo-chart.html#delay-times-tempo-bpm-chart",
    ),
    (re.compile(r"the table below(?= shows the frequency)", re.I), "#lfo-frequencies"),
]


def link_chart_refs(escaped: str) -> str:
    """Turn ‘see the Envelope Times chart below’ (and similar) into in-page links."""
    for pat, href in CHART_REF_PATTERNS:
        escaped = pat.sub(lambda m, h=href: f'<a href="{h}">{m.group(0)}</a>', escaped)
    return escaped


SECTIONS_AND_RE = re.compile(r"\bSections?\s+(\d+)\s+and\s+(\d+)\b", re.I)
SECTION_REF_RE = re.compile(
    r"\bSection\s+(\d+)\s*[—–\-]\s*((?:[^<.;]|&[a-z#0-9]+;|<(?!/a>)[^>]*>)+?)"
    r"(?=[.;,)\]\"']|<|$|\s+for\s|\s+and\s|\s+in\s|\s+on\s|\s+with\s|\s+where\s|\s+which\s|\s+is\s|\s+are\s|\s+was\s|\s+will\s|\s+can\s|\s+has\s|\s+have\s|\s+explains\b)",
    re.I,
)


def link_section_refs(escaped: str, current_file: str | None = None) -> str:
    """Link cross-references like ‘see Section 5 — Preset/Track Parameters’."""
    def link_num(num: str, hint: str = "") -> str:
        href = section_href(int(num), hint, current_file)
        return f'<a class="refer-to" href="{html.escape(href, quote=True)}">'

    def repl_section(m: re.Match[str]) -> str:
        num, hint = m.group(1), m.group(2).strip()
        return f'{link_num(num, hint)}Section {num} — {hint}</a>'

    def repl_and(m: re.Match[str]) -> str:
        n1, n2 = m.group(1), m.group(2)
        h1 = section_href(int(n1), "", current_file)
        h2 = section_href(int(n2), "", current_file)
        return (
            f'Sections <a class="refer-to" href="{html.escape(h1, quote=True)}">{n1}</a> '
            f'and <a class="refer-to" href="{html.escape(h2, quote=True)}">{n2}</a>'
        )

    parts = re.split(r"(<[^>]+>)", escaped)
    skip = False
    for i, part in enumerate(parts):
        if part.startswith("<"):
            if part.startswith('<a ') or part.startswith('<a>'):
                skip = True
            elif part == "</a>":
                skip = False
            continue
        if skip:
            continue
        part = SECTIONS_AND_RE.sub(repl_and, part)
        parts[i] = SECTION_REF_RE.sub(repl_section, part)
    return "".join(parts)


def section_ref_join(prev: str, nxt: str) -> str | None:
    """Rejoin section cross-references split across transcript lines."""
    prev_st = prev.rstrip()
    nxt_st = nxt.strip()
    if prev_st.endswith("refer to") and SECTION_LINE_RE.match(nxt_st):
        return f"{prev_st} {nxt_st}"
    if re.search(r"Section\s+\d+\s*[—–\-]\s*$", prev_st):
        if re.match(r"^[A-Za-z(/].*", nxt_st) and len(nxt_st) < 100:
            return f"{prev_st} {nxt_st}"
    if re.search(r"Section\s+\d+\s*[—–\-]\s+\S", prev_st) and not re.search(r"[.!?)]$", prev_st):
        if (
            len(nxt_st.split()) <= 8
            and re.match(r"^[A-Za-z(/].*", nxt_st)
            and not is_flush_line(nxt_st)
            and not nxt_st.startswith("•")
            and not re.match(r"^(Press|Note:|Tip:|When|If|The|This|These|You|Transmit|Receive)\b", nxt_st)
        ):
            return f"{prev_st} {nxt_st}"
    return None


def format_range_html(rng: str) -> str:
    rng = re.sub(r"\s+", " ", rng).strip()
    if not rng:
        return ""
    if not re.search(r"\bRanges?:", rng):
        parts = re.split(r"\s+(?=Held Range:)", rng, maxsplit=1, flags=re.I)
        bits = [f"Range: {link_chart_refs(html.escape(parts[0]))}"]
        if len(parts) > 1:
            bits.append(link_chart_refs(html.escape(parts[1])))
        return "<br>".join(bits)
    if NAMED_RANGE_CLAUSE_SPLIT.search(rng):
        parts = NAMED_RANGE_CLAUSE_SPLIT.split(rng)
        parts = [p.strip() for p in parts if p.strip()]
        return "<br>".join(link_chart_refs(html.escape(p)) for p in parts)
    return link_chart_refs(html.escape(rng))


def unwrap(lines: list[str]) -> list[str]:
    """Join hyphenated wraps and lowercase sentence continuations; keep own-line gaps."""
    paras: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        if len(buf) == 1:
            paras.append(buf[0].strip())
        else:
            text = " ".join(x.strip() for x in buf)
            text = re.sub(r"\s+", " ", text).strip()
            paras.append(text)
        buf.clear()

    for ln in lines:
        s = ln.strip()
        if not s:
            flush()
            paras.append("")
            continue
        if buf:
            prev = buf[-1]
            joined = (
                range_join(prev, s)
                or yesno_join(prev, s)
                or bullet_join(prev, s)
                or tip_join(prev, s)
                or token_hyphen_join(prev, s)
                or table_row_join(prev, s)
                or section_ref_join(prev, s)
            )
            if joined is not None:
                buf[-1] = joined
                continue
            if prev.rstrip().endswith("Up/Down") and re.match(r"^Arrow buttons\b", s):
                buf[-1] = f"{prev.rstrip()} {s}"
                continue
            if prev.rstrip().endswith("the Display") and s.startswith("Locations are numbered"):
                buf[-1] = f"{prev.rstrip()} {s}"
                continue
            hyphen = bool(re.search(r"[A-Za-z]-$", prev))
            continuation = _is_continuation(s)
            if "...." in s or "...." in prev:
                flush()
                buf.append(s)
                continue
            if hyphen and continuation:
                buf[-1] = prev[:-1] + s
                continue
            if is_gutter_twocol_row(s):
                flush()
                buf.append(s)
                continue
            if (
                not is_flush_line(s)
                and not is_flush_line(prev)
                and not re.search(r"[.!?]$", prev)
                and (
                    continuation
                    or MID_PHRASE_END.search(prev.rstrip())
                    or (len(prev) >= 40 and MID_PHRASE_END.search(prev))
                    or (len(prev) >= 50 and len(s) >= 45)
                )
            ):
                buf.append(s)
                continue
        flush()
        buf.append(s)
    flush()
    collapsed: list[str] = []
    blank = False
    for p in paras:
        if p == "":
            if not blank:
                collapsed.append("")
            blank = True
        else:
            collapsed.append(p)
            blank = False
    return expand_defn_table_lines(merge_dangling_prose(join_page_wraps(collapsed)))


def join_page_wraps(paras: list[str]) -> list[str]:
    """Rejoin sentences split by a form-feed blank, not headings followed by a new paragraph."""
    out: list[str] = []
    i = 0
    while i < len(paras):
        cur = paras[i]
        if (
            cur
            and i + 2 < len(paras)
            and paras[i + 1] == ""
            and paras[i + 2]
            and not re.search(r"[.!?]$", cur)
            and (
                not is_flush_line(cur)
                or is_bullet_item(cur)
                or TIP_RE.match(cur)
                or split_twocol_row(cur)
            )
            and _is_continuation(paras[i + 2])
            and not is_flush_line(paras[i + 2])
        ):
            nxt = paras[i + 2]
            if cur.endswith("-") and nxt[:1].islower():
                out.append(cur[:-1] + nxt)
            else:
                out.append(cur + " " + nxt)
            i += 3
            continue
        out.append(cur)
        i += 1
    return out


def classify(line: str) -> str:
    if not line:
        return "blank"
    if TIP_RE.match(line):
        return "tip"
    if RANGE_RE.match(line):
        if RANGE_RE.match(line).group(1).strip() in ("Song", "Seq"):
            return "named-range-cont"
        return "range"
    if match_named_range_param(line):
        return "range"
    if ALGO_RE.match(line) and len(line) < 48:
        return "algo"
    if SECTION_LINE_RE.match(line):
        return "para"
    if PAGE_TITLE_RE.match(line) and not NOT_HEADING_START.match(line) and ". " not in line:
        return "h2"
    if line.endswith("?") and 8 <= len(line) < 60 and line[0].isupper():
        return "h2"
    if line.endswith("Parameters") and len(line) < 60 and not line.startswith("•"):
        return "h2"
    if re.match(r"^(Dual|Parallel|Serial) Effects$", line):
        return "h2"
    if line in ("Warning", "Important") or line.endswith(" Warning"):
        return "h3"
    toc = toc_heading_kind(line)
    if toc:
        return toc
    if is_enum_heading(line):
        return "h4"
    if (
        line.endswith(":")
        and 3 <= len(line) < 50
        and line[0].isupper()
        and not line.lower().startswith("note")
        and not NOT_HEADING_START.match(line)
        and not re.search(r"\b(the|are|is|to|for|with|this|shows|then)\b", line, re.I)
        and not line.startswith("•")
    ):
        return "h3"
    if split_bullet_grid_row(line):
        return "bullet-grid"
    if setting_header_cells(line):
        return "callouts"
    if is_yesno_row(line):
        return "callouts"
    if numeric_lookup_cells(line) or numeric_header_cells(line) or delay_chart_parts(line):
        return "num-table"
    if split_twocol_row(line):
        return "table"
    if is_multicolumn(line):
        parts = [p for p in re.split(r"\s{2,}", line.strip()) if p]
        compact = all(re.fullmatch(r"[A-Z0-9*][A-Z0-9+\-/*()=.*]*", p) for p in parts)
        if (
            compact
            and all(is_vfd_text(p) for p in parts)
            and any(VFD_EQ_RE.search(p) for p in parts)
        ):
            return "vfd"
        if any(c.islower() for c in line):
            return "callouts"
        return "p"
    if is_param_heading(line):
        return "h4"
    if (
        len(line.split()) == 1
        and 8 <= len(line) <= 24
        and line[0].isupper()
        and not line.isupper()
        and not line.endswith((".", ",", ":", ";"))
        and not re.match(r"^[A-Z][A-Za-z-]+$", line)
    ):
        return "h3"
    if is_prose_heading(line):
        return "h3"
    if gated_reverb_diagram_title(line):
        return "h4"
    if is_vfd_line(line):
        return "vfd"
    return "p"


def is_vfd_line(line: str) -> bool:
    if any(c.islower() for c in line):
        return False
    hits = VFD_EQ_RE.findall(line)
    if len(hits) < 2 or len(line) > 90:
        return False
    remainder = VFD_EQ_RE.sub("", line)
    remainder = re.sub(r"[\s,;:()]+", "", remainder)
    return len(remainder) < 8 and is_vfd_text(line)


def load_vfd_screens() -> dict:
    if not VFD_SCREENS_PATH.exists():
        return {"screens": {}, "by_trigger": {}, "by_callouts": {}}
    return json.loads(VFD_SCREENS_PATH.read_text())


def _trigger_next_ok(need: str, nxt: str) -> bool:
    """True when the following line is the caption for this screen, not a later mention."""
    if not need:
        return True
    n = nxt.lstrip("• ").strip()
    return n.upper().startswith(need.upper())


def match_vfd_trigger(
    line: str, catalog: dict, used: dict[str, int], nxt: str = ""
) -> str | None:
    """Return a screen id. List values are consumed in order for repeated phrases."""
    lower = line.lower()
    for phrase, sid in catalog.get("by_trigger", {}).items():
        if phrase.lower() not in lower:
            continue
        if isinstance(sid, dict):
            if not _trigger_next_ok(sid.get("if_next", ""), nxt):
                continue
            return sid["id"]
        if isinstance(sid, list):
            if sid and isinstance(sid[0], dict):
                for item in sid:
                    if not _trigger_next_ok(item.get("if_next", ""), nxt):
                        continue
                    return item["id"]
                continue
            key = phrase.lower()
            idx = used.get(key, 0)
            if idx >= len(sid):
                continue
            used[key] = idx + 1
            return sid[idx]
        return sid
    return None


def split_cols(line: str) -> list[str]:
    return [p for p in re.split(r"\s{2,}", line.strip()) if p]


def split_bullet_grid_row(line: str) -> list[str] | None:
    """Two or more short bullets sharing a PDF line (`• left          • right`)."""
    s = line.strip()
    if not s.startswith("•"):
        return None
    parts = split_cols(s)
    if len(parts) < 2 or not all(p.startswith("•") for p in parts):
        return None
    if any(len(p) > 58 for p in parts):
        return None
    return parts


NUM_CELL_RE = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)$")
LOOKUP_CAPTION_RE = re.compile(r"^[A-Z][A-Z ]{4,40}$")
HEADER_ATOM_RE = re.compile(
    r"^(?:time|value|\(in[ ]?\w+\))$",
    re.I,
)
HEADER_GROUP_RE = re.compile(
    r"^(?:time|value)(?:\s+\(in\s+\w+\))?$",
    re.I,
)
DELAY_LABEL_RE = re.compile(
    r"^(?:BPM|1/4 NOTE|1/8th NOTE|1/8 TRIPLET|1/16th NOTE)$",
    re.I,
)
DELAY_HEADERS = ["BPM", "1/4 NOTE", "1/8th NOTE", "1/8 TRIPLET", "1/16th NOTE"]
DELAY_TEMPO_CHART_FNAME = "12-delay-tempo-chart.html"
DELAY_TEMPO_BPM_CHART_ID = "delay-times-tempo-bpm-chart"
DELAY_TEMPO_CHART_INTRO_RE = re.compile(
    r"^Delay Times/Tempo BPM Chart\b",
    re.I,
)
DELAY_TEMPO_CHART_INTRO = (
    "This chart shows the relationship between delay times and tempo beats per "
    "minute. Values shown are accurate to 2 decimal places—since most delay "
    "devices are not accurate to 2 decimal places, you may have to round off "
    "these values. You can use this chart to set the effect delay times to sync "
    "to your sequence or song."
)
DELAY_TEMPO_CHART_TIP = (
    "Assign a controller to modulate the effect delay times, ands select a "
    "specified minimum and maximum range so that you can create unique "
    "poly-rhythms in real-time."
)
DELAY_TEMPO_CALC_NOTES = [
    ("1/4 note", 60000),
    ("Dotted 1/4", 90000),
    ("1/8 note", 30000),
    ("Dotted 1/8", 45000),
    ("1/8 triplet", 20000),
    ("1/16 note", 15000),
    ("Dotted 1/16", 22500),
]
SETTING_HEADERS = [
    "Setting",
    "Local Voices Affected",
    "MIDI Reception Affected",
    "MIDI Transmission Affected",
]


def setting_header_cells(line: str) -> list[str] | None:
    compact = re.sub(r"\s+", " ", line.strip())
    if compact == " ".join(SETTING_HEADERS):
        return list(SETTING_HEADERS)
    return None


def numeric_lookup_cells(line: str) -> list[str] | None:
    """A row of a printed numeric chart (LFO FREQUENCIES, delay/tempo, …)."""
    s = line.strip()
    if not s or RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return None
    for parts in (split_cols(s), s.split()):
        if len(parts) >= 5 and all(NUM_CELL_RE.match(p) for p in parts):
            return list(parts)
    return None


def delay_tempo_ms_values(bpm: int) -> list[str]:
    """Delay times in ms for quarter, eighth, eighth-triplet, and sixteenth notes."""
    return [
        f"{60000 / bpm:.2f}",
        f"{30000 / bpm:.2f}",
        f"{20000 / bpm:.2f}",
        f"{15000 / bpm:.2f}",
    ]


def delay_tempo_bpm_chart_pairs() -> list[tuple[int, int]]:
    """Two-column layout: each row pairs BPM n with n+45 (covers 40–205 and 85–250)."""
    return [(40 + i, 85 + i) for i in range(166)]


def render_delay_tempo_bpm_chart(terms: dict[str, list[str]]) -> str:
    headers = DELAY_HEADERS * 2
    caption = "Delay Times/Tempo BPM Chart"
    parts = [
        f'<table class="data-table delay-tempo-chart" id="{DELAY_TEMPO_BPM_CHART_ID}">',
        f'<caption><a href="#{DELAY_TEMPO_BPM_CHART_ID}">{html.escape(caption)}</a></caption>',
        "<thead><tr>",
        "".join(f"<th>{apply_tags(h, terms)}</th>" for h in headers),
        "</tr></thead><tbody>",
    ]
    for left_bpm, right_bpm in delay_tempo_bpm_chart_pairs():
        row: list[str] = [
            str(left_bpm),
            *delay_tempo_ms_values(left_bpm),
            str(right_bpm),
            *delay_tempo_ms_values(right_bpm),
        ]
        parts.append(
            "<tr>"
            + "".join(f"<td>{html.escape(cell)}</td>" for cell in row)
            + "</tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def render_delay_tempo_calculator() -> str:
    rows = "".join(
        f'<tr><th scope="row">{html.escape(label)}</th>'
        f'<td class="delay-ms" data-numerator="{num}">—</td></tr>'
        for label, num in DELAY_TEMPO_CALC_NOTES
    )
    return (
        '<section class="delay-tempo-calculator" aria-labelledby="delay-tempo-calculator-heading">'
        '<h2 id="delay-tempo-calculator-heading">Delay Time Calculator</h2>'
        "<p>Enter a tempo to see sync delay times in milliseconds.</p>"
        '<form class="delay-tempo-calc-form" id="delay-tempo-calc" action="#">'
        '<label for="delay-tempo-bpm-input">Tempo (BPM)</label>'
        '<input type="number" id="delay-tempo-bpm-input" name="bpm" '
        'min="1" max="999" step="1" value="120" inputmode="numeric">'
        "</form>"
        '<table class="data-table delay-tempo-calc-results">'
        "<thead><tr><th>Note length</th><th>Delay (ms)</th></tr></thead>"
        f"<tbody>{rows}</tbody></table></section>"
    )


def build_delay_tempo_chart_page_body(terms: dict[str, list[str]]) -> str:
    intro = apply_tags(DELAY_TEMPO_CHART_INTRO, terms)
    tip = apply_tags(DELAY_TEMPO_CHART_TIP, terms)
    return (
        f"<p>{intro}</p>\n"
        f"{render_delay_tempo_calculator()}\n"
        f'<aside class="tip"><p>{tip}</p></aside>\n'
        f"{render_delay_tempo_bpm_chart(terms)}"
    )


def is_delay_tempo_chart_intro(line: str) -> bool:
    return bool(DELAY_TEMPO_CHART_INTRO_RE.match(line.strip()))


def skip_delay_tempo_chart_section(lines: list[str], i: int) -> int:
    """Skip intro, OCR chart rows, and the following tip (moved to its own page)."""
    j = i + 1
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        if TIP_RE.match(s):
            return j + 1
        if (
            classify(lines[j]) == "num-table"
            or delay_chart_parts(s)
            or is_numeric_chart_line(s)
        ):
            j += 1
            continue
        break
    return j


def delay_chart_parts(line: str) -> list[str] | None:
    """BPM / note-length header row, or a mixed header+data row of that chart."""
    s = line.strip()
    if not s or RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return None
    parts = split_cols(s)
    if len(parts) < 5:
        return None
    if not all(DELAY_LABEL_RE.match(p) or NUM_CELL_RE.match(p) for p in parts):
        return None
    if any(DELAY_LABEL_RE.match(p) for p in parts):
        return parts
    return None


YESNO_TOKEN_RE = re.compile(r"^(?:YES|NO|ON|OFF)$", re.I)
HEADER_WRAP_SKIP = {
    "mode", "note", "memory", "glide", "staccato", "legato", "yes", "no",
}


def is_yesno_row(line: str) -> bool:
    """A matrix row whose cells are mostly YES/NO (GLIDE MODES, MIDI status)."""
    s = line.strip()
    if not s or RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return False
    parts = split_cols(s)
    if len(parts) < 4:
        return False
    flags = sum(1 for p in parts if YESNO_TOKEN_RE.match(p))
    return flags >= 3 and flags >= len(parts) - 2


def is_chart_paren_row(line: str) -> bool:
    return bool(re.fullmatch(r"\([^)]{3,48}\)", line.strip()))


def is_chart_header_row(line: str) -> bool:
    s = line.strip()
    if not s or is_yesno_row(s) or is_chart_paren_row(s) or is_bullet_item(s):
        return False
    if RANGE_RE.match(s) or TIP_RE.match(s):
        return False
    parts = split_cols(s)
    if len(parts) < 3:
        return False
    if any(len(p) > 32 or p.endswith(".") or VFD_EQ_RE.search(p) for p in parts):
        return False
    return True


def is_header_wrap_atom(line: str) -> bool:
    """Orphan wrap under a header row (`Retrigger`)."""
    s = line.strip()
    return bool(
        s
        and " " not in s
        and 6 <= len(s) <= 24
        and s[0].isupper()
        and not s.isupper()
        and s.isalpha()
        and s.lower() not in ("warning", "important")
    )


def yesno_join(prev: str, s: str) -> str | None:
    """Rejoin a wrapped matrix row label with its YES/NO cells."""
    if not prev or not is_yesno_row(s) or is_yesno_row(prev):
        return None
    if is_multicolumn(prev) or RANGE_RE.match(prev) or TIP_RE.match(prev):
        return None
    if len(split_cols(prev)) > 1 or setting_header_cells(prev):
        return None
    if is_bullet_item(prev) or PAGE_TITLE_RE.match(prev) or is_param_heading(prev):
        return None
    if toc_heading_kind(prev) or is_prose_heading(prev):
        return None
    if is_chart_paren_row(prev) or is_header_wrap_atom(prev):
        return None
    if prev.endswith((".", ":", ";", "?", "!")):
        return None
    if prev.lower().startswith(("note:", "important:")):
        return None
    return f"{prev} {s}"


def expand_glued_header(parts: list[str], want: int) -> list[str]:
    """Split a glued title-case cell when the row is one column short."""
    if len(parts) >= want or want - len(parts) != 1:
        return list(parts)
    best_i, best_len = -1, 0
    for i, p in enumerate(parts):
        words = p.split()
        if len(words) >= 2 and all(w[:1].isupper() for w in words if w[:1].isalpha()):
            if len(p) > best_len:
                best_i, best_len = i, len(p)
    if best_i < 0:
        return list(parts)
    words = parts[best_i].split()
    return parts[:best_i] + [words[0], " ".join(words[1:])] + parts[best_i + 1 :]


def merge_matrix_headers(rows: list[list[str]], ncols: int) -> list[str]:
    if not rows:
        return []
    stacked: list[list[str]] = []
    for row in rows:
        if len(row) == 1 and stacked:
            prev = stacked[-1]
            idx = None
            for k, c in enumerate(prev):
                if c and c.lower() not in HEADER_WRAP_SKIP:
                    idx = k
            if idx is None:
                idx = max(range(len(prev)), key=lambda k: len(prev[k]))
            prev[idx] = f"{prev[idx]} {row[0]}".strip()
        else:
            stacked.append(list(row))
    if not stacked:
        return []
    if len(stacked) == 1:
        row = expand_glued_header(stacked[0], ncols)
        return (row + [""] * ncols)[:ncols]
    a, b = stacked[0], stacked[1]
    mode = lambda p: p.upper() == "MODE"
    if b and mode(b[0]) and len(b) == ncols:
        a = expand_glued_header(a, ncols - 1)
        out = [b[0]]
        for i in range(ncols - 1):
            top = a[i] if i < len(a) else ""
            bot = b[i + 1] if i + 1 < len(b) else ""
            out.append(f"{top} {bot}".strip())
        return out
    if a and mode(a[0]) and len(a) == ncols and len(b) == ncols - 1:
        out = [a[0]]
        for i in range(ncols - 1):
            top = a[i + 1] if i + 1 < len(a) else ""
            bot = b[i] if i < len(b) else ""
            out.append(f"{top} {bot}".strip())
        return out
    width = max(len(a), len(b), ncols)
    a = a + [""] * (width - len(a))
    b = b + [""] * (width - len(b))
    return [f"{x} {y}".strip() for x, y in zip(a, b)][:ncols]


def numeric_header_cells(line: str) -> list[str] | None:
    s = line.strip()
    if not s or RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return None
    parts = split_cols(s)
    if len(parts) >= 3 and all(HEADER_GROUP_RE.match(p) or HEADER_ATOM_RE.match(p) for p in parts):
        return parts
    atoms = s.split()
    if len(atoms) >= 4 and all(HEADER_ATOM_RE.match(p) for p in atoms):
        return atoms
    groups = re.findall(r"(?i)(?:time|value)\s*\(in\s+\w+\)", s)
    if len(groups) >= 3:
        return groups
    return None


def is_lookup_caption(line: str) -> bool:
    s = line.strip()
    return bool(LOOKUP_CAPTION_RE.match(s)) and 1 <= s.count(" ") <= 3


def is_short_label_name(name: str) -> bool:
    """ALL-CAPS row labels in lookup tables (WHEEL, FX-SW, *OFF*)."""
    if re.fullmatch(r"\*[A-Z]+\*", name):
        return True
    return bool(re.fullmatch(r"[A-Z]{2,8}(?:-[A-Z]{2,6})?", name))


def is_column_header(name: str, desc: str) -> bool:
    """Printed column captions such as Mod Source | Modulation effect derived from."""
    if not is_prose_cell(desc):
        return False
    if re.search(r"\b(has|is|are|was|will|can|have)\b", desc, re.I):
        return False
    return bool(
        re.fullmatch(r"(?:[A-Z][a-z]+(?: [A-Z][a-z]+)?){1,2}", name)
        and 4 <= len(name) <= 32
        and 8 <= len(desc) <= 72
        and not name.endswith(":")
        and not desc.endswith(":")
    )


def is_gutter_twocol_row(s: str) -> bool:
    """True when the line still has the PDF's name/description column gutter."""
    if not re.search(r"\s{2,}", s):
        return False
    return bool(split_twocol_row(s) or split_twocol_row(s, in_table=True))


def split_off_row_trailer(line: str) -> list[str]:
    m = re.search(
        r"(\*[A-Z]+\*.*?no modulation)\s+(For more information about.+)",
        line,
        re.I,
    )
    if m:
        return [m.group(1).strip(), m.group(2).strip()]
    return [line]


def expand_collapsed_defn_line(line: str) -> list[str]:
    """Split OCR/unwrap merges of 2-column lookup rows back into separate lines."""
    s = line.strip()
    if not s or not is_defn_table_candidate(s):
        return [s]
    matches = list(DEFN_ROW_SPLIT.finditer(s))
    if not matches:
        return [s]
    if len(matches) == 1 and matches[0].start() == 0:
        return [s]
    parts: list[str] = []
    prefix = s[: matches[0].start()].strip()
    if prefix:
        parts.append(prefix)
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(s)
        chunk = s[start:end].strip()
        if chunk:
            parts.append(chunk)
    return parts or [s]


def is_defn_table_candidate(line: str) -> bool:
    """Skip prose; only split lines that are clearly merged lookup-table rows."""
    if re.search(
        r"\b(refer to|For a complete|Controls the|Setting this|This parameter|algorithm found)\b",
        line,
        re.I,
    ):
        return False
    lower = sum(1 for c in line if c.islower())
    if lower > max(12, len(line) // 3):
        return False
    return True


def should_expand_defn_line(line: str) -> bool:
    """Only split lines that clearly contain several merged lookup-table rows."""
    if not is_defn_table_candidate(line):
        return False
    matches = list(DEFN_ROW_SPLIT.finditer(line))
    if len(matches) >= 2:
        return True
    if len(matches) == 1 and matches[0].start() > 0:
        prefix = line[: matches[0].start()]
        return bool(re.search(r"(?:Mod Source|derived from)\s*$", prefix, re.I))
    return False


def expand_defn_table_lines(paras: list[str]) -> list[str]:
    out: list[str] = []
    for p in paras:
        if not p:
            out.append(p)
            continue
        if should_expand_defn_line(p):
            out.extend(expand_collapsed_defn_line(p))
            continue
        out.extend(split_off_row_trailer(p))
    return out


def is_table_name(name: str, *, in_table: bool = False, desc: str = "") -> bool:
    """Left-column tokens like DRUM-FX1, 00 PATCH, *VOICE*, SEND/RECV, F0 7E."""
    if re.fullmatch(r"<[^>]+>", name):
        return True
    if re.fullmatch(r"[LCR*-]{4,10}", name):
        return True
    if re.fullmatch(r"[0-9A-F]{2}(?: [0-9A-F]{2})+", name):
        return True
    if re.fullmatch(r"[0-9A-F]{2}", name):
        return bool(re.match(r"^(sub-ID|EOX\b|ID of |Universal )", desc, re.I))
    if not TABLE_NAME_RE.match(name):
        return False
    if is_short_label_name(name):
        return True
    return bool(re.search(r"[0-9*/\-]", name) or "*" in name)


def is_prose_cell(desc: str) -> bool:
    return any(c.islower() for c in desc) and len(desc) >= 3


def is_twocol_header(line: str) -> bool:
    """Lowercase column captions (`for this setting:`) — not diagram labels (`BankSet U0:`)."""
    parts = split_cols(line.strip())
    if len(parts) != 2:
        return False
    name, desc = parts
    return (
        name.endswith(":")
        and desc.endswith(":")
        and name[:1].islower()
        and desc[:1].islower()
        and 4 <= len(name) <= 40
        and 4 <= len(desc) <= 48
        and not RANGE_RE.match(line)
        and not TIP_RE.match(line)
    )


def looks_like_title(s: str) -> bool:
    words = re.findall(r"[A-Za-z0-9]+", s)
    if len(words) < 4 or s.endswith((".", ",", ";", ":")):
        return False
    caps = sum(1 for w in words if w[:1].isupper())
    return caps >= len(words) - 1


def cell_complete(desc: str) -> bool:
    return bool(re.search(r"[.!?)]$", desc.rstrip()))


def match_table_name_prefix(s: str) -> tuple[str, str] | None:
    """Name + prose when OCR collapsed the gutter to a single space (NORMAL-FX1 A normal…)."""
    words = s.split()
    if len(words) < 2:
        return None
    two = f"{words[0]} {words[1]}"
    if len(words) > 2:
        rest = s[len(two) :].lstrip()
        if is_table_name(two, in_table=True, desc=rest) and is_prose_cell(rest):
            if rest[:1].isupper() or re.match(r"sub-ID\b", rest):
                return two, rest
    rest = s[len(words[0]) :].lstrip()
    if is_table_name(words[0], in_table=True, desc=rest) and is_prose_cell(rest):
        if rest[:1].isupper() or re.match(r"sub-ID\b", rest):
            return words[0], rest
    return None


def split_twocol_row(line: str, *, in_table: bool = False) -> tuple[str, str] | None:
    """Two-column name | description if the PDF used a gutter of 2+ spaces (or 1 in a table run)."""
    s = line.strip()
    if not s or RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return None
    if s.lower().startswith(("note:", "important:")):
        return None
    parts = split_cols(s)
    if len(parts) == 2:
        name, desc = parts
        if is_twocol_header(s):
            return name, desc
        if is_column_header(name, desc):
            return name, desc
        if is_table_name(name, in_table=in_table, desc=desc) and is_prose_cell(desc):
            if (
                desc[:1].islower()
                and not re.match(r"sub-ID\b", desc)
                and not (in_table or is_short_label_name(name))
            ):
                return None
            return name, desc
        return None
    m = re.match(r"^((?:[A-Z][a-z]+(?: [A-Z][a-z]+)?){1,2})\s+(.+)$", s)
    if m:
        name, desc = m.group(1), m.group(2)
        if is_column_header(name, desc):
            return name, desc
    if in_table:
        return match_table_name_prefix(s)
    prefixed = match_table_name_prefix(s)
    if prefixed and is_short_label_name(prefixed[0]):
        return prefixed
    return None


def is_table_desc_wrap(s: str, last_desc: str, *, row_follows: bool = False) -> bool:
    if not s:
        return False
    if split_twocol_row(s) or split_twocol_row(s, in_table=True):
        return False
    if RANGE_RE.match(s) or TIP_RE.match(s) or is_bullet_item(s):
        return False
    if PAGE_TITLE_RE.match(s) or is_param_heading(s) or toc_heading_kind(s) or (s.startswith("Section ") and "—" in s):
        return False
    if s.lower().startswith(("note:", "important:")) or looks_like_title(s) or is_prose_heading(s):
        return False
    if re.match(r"^(?:For more information|See Section \d+)", s, re.I):
        return False
    kind = classify(s)
    if kind in ("h1", "h2", "h3", "h4", "range", "tip", "algo", "vfd", "callouts"):
        return False
    if _is_continuation(s) or last_desc.rstrip().endswith((",", ";", "—", "–", "-")):
        return True
    if MID_PHRASE_END.search(last_desc) and not cell_complete(last_desc):
        return True
    if not cell_complete(last_desc):
        return True
    if NOT_HEADING_START.match(s) and s[:1].isupper():
        return False
    return row_follows


def is_partial_callout(line: str) -> bool:
    s = line.strip()
    if not s or RANGE_RE.match(s) or split_twocol_row(s):
        return False
    if numeric_lookup_cells(s) or numeric_header_cells(s):
        return False
    parts = split_cols(s)
    return (
        2 <= len(parts) <= 3
        and any(c.islower() for c in s)
        and all(len(p) < 50 for p in parts)
    )


def consume_callout_rows(lines: list[str], i: int) -> tuple[list[list[str]], int]:
    rows: list[list[str]] = []
    while i < len(lines):
        s = lines[i].strip()
        if not s:
            break
        if classify(lines[i]) == "callouts" or is_partial_callout(s) or is_yesno_row(s):
            rows.append(setting_header_cells(s) or split_cols(s))
            i += 1
            continue
        break
    return rows, i


def format_table_name_html(name: str, terms: dict[str, list[str]]) -> str:
    if is_vfd_text(name):
        return f'<span class="lcd">{html.escape(name)}</span>'
    return apply_tags(name, terms)


def render_defn_table(rows: list[list], terms: dict[str, list[str]]) -> str:
    parts = ['<table class="defn-table">']
    headers = [r for r in rows if r[2]]
    if headers:
        parts.append("<thead>")
        for name, desc, _header in headers:
            parts.append(
                "<tr>"
                f"<th>{apply_tags(name, terms)}</th>"
                f"<th>{apply_tags(desc, terms)}</th>"
                "</tr>"
            )
        parts.append("</thead>")
    parts.append("<tbody>")
    for name, desc, header in rows:
        if header:
            continue
        parts.append(
            "<tr>"
            f"<td>{format_table_name_html(name, terms)}</td>"
            f"<td>{apply_tags(desc, terms)}</td>"
            "</tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def consume_defn_table(
    lines: list[str], i: int, terms: dict[str, list[str]]
) -> tuple[str | None, int]:
    rows: list[list] = []
    j = i
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k >= len(lines):
                break
            nxt = lines[k].strip()
            if rows and (
                split_twocol_row(nxt)
                or split_twocol_row(nxt, in_table=True)
                or is_table_desc_wrap(
                    nxt, rows[-1][1], row_follows=table_row_ahead(lines, k)
                )
            ):
                j = k
                continue
            break
        parsed = split_twocol_row(s) or (
            split_twocol_row(s, in_table=True) if rows else None
        )
        if parsed:
            name, desc = parsed
            header = is_twocol_header(s) or is_column_header(name, desc)
            rows.append([name, desc, header])
            j += 1
            continue
        if rows and is_table_desc_wrap(
            s, rows[-1][1], row_follows=table_row_ahead(lines, j)
        ):
            rows[-1][1] = f"{rows[-1][1]} {s}"
            j += 1
            continue
        break
    body = [r for r in rows if not r[2]]
    if len(body) < 2:
        return None, i
    return render_defn_table(rows, terms), j


def is_bullet_grid_orphan(s: str, nxt: str, rows: list[list[str]]) -> bool:
    """Odd leftover (`• Wave Page Parameters`) after a 2-column bullet block."""
    if not is_bullet_item(s) or split_bullet_grid_row(s):
        return False
    if len(s) > 55:
        return False
    text = s.lstrip("• ").strip()
    seen = {c.lstrip("• ").strip() for row in rows for c in row}
    if text in seen:
        return False
    if nxt and _is_continuation(nxt):
        return False
    if (
        nxt
        and NOT_HEADING_START.match(nxt)
        and len(nxt) > 60
        and not nxt.startswith(("For more", "See ", "Refer "))
    ):
        return False
    return True


EFFECT_PARAM_REF_ROWS = (
    ("FX2- -REVRB", "PAN"),
    ("DRY", "DDL REGEN L"),
    ("DDL MIX", "DAMPING"),
    ("LEVEL", "DELAY TIME L and R"),
)

EFFECT_PARAM_REF_HEADER_RE = re.compile(
    r"^FX2- -REVRB\s+PAN\s+DRY\s+DDL REGEN L\s+DDL MIX DAMPING\s*$"
)

EFFECT_PARAM_REF_TRAILER_RE = re.compile(
    r"^LEVEL\s+DELAY TIME L and R\s+("
    r"For a complete description of these parameters,\s*refer to the.+)$",
    re.I,
)

EFFECT_PARAM_REF_CROSSREF_RE = re.compile(
    r"^For a complete description of these parameters,\s*refer to the\s+"
    r".+algorithm found earlier in this section\.?\s*$",
    re.I,
)


def render_effect_param_ref_table() -> str:
    parts = ['<table class="param-cols"><tbody>']
    for left, right in EFFECT_PARAM_REF_ROWS:
        parts.append(
            "<tr>"
            f'<td><span class="param">{html.escape(left)}</span></td>'
            f'<td><span class="param">{html.escape(right)}</span></td>'
            "</tr>"
        )
    parts.append("</tbody></table>")
    return "".join(parts)


def consume_effect_param_ref_table(
    lines: list[str],
    i: int,
    terms: dict[str, list[str]],
    fname: str,
) -> tuple[str | None, int]:
    s = lines[i].strip()
    if not EFFECT_PARAM_REF_HEADER_RE.match(s):
        return None, i
    html = render_effect_param_ref_table()
    j = i + 1
    if j < len(lines) and lines[j].strip():
        nxt = lines[j].strip()
        cross_ref = None
        m = EFFECT_PARAM_REF_TRAILER_RE.match(nxt)
        if m:
            cross_ref = m.group(1)
        elif EFFECT_PARAM_REF_CROSSREF_RE.match(nxt):
            cross_ref = nxt
        if cross_ref:
            html += f'<p>{apply_tags(cross_ref, terms, source_file=fname)}</p>'
            j += 1
    return html, j


def split_col_row(line: str, *, min_gap: int = 4) -> list[str] | None:
    s = line.strip()
    if not s:
        return None
    parts = [p.strip() for p in re.split(rf"\s{{{min_gap},}}", s) if p.strip()]
    return parts if len(parts) >= 2 else None


PARAM_COL_EXCLUDE_RE = re.compile(
    r"FX-?[12]?\s*(?:Left|Right)"
    r"|(?:Left|Right)\s+(?:Output|Delay|Regen|LFO|Main|Echo|Shifter|Vc|Pre-Dist|Level)"
    r"|^\(LFO\)"
    r"|\bOutput Level\b"
    r"|\bPre-Dist\b",
    re.I,
)
LABEL_CELL_RE = re.compile(r"^[A-Za-z0-9*][A-Za-z0-9 ()+\-/]*:?$")


def is_param_col_cell(cell: str) -> bool:
    if not cell or len(cell) > 24 or NOT_HEADING_START.match(cell):
        return False
    if cell.endswith(".") and len(cell) > 12:
        return False
    if len(cell) == 1:
        return cell.isalnum()
    return bool(LABEL_CELL_RE.match(cell))


def split_param_col_row(line: str) -> list[str] | None:
    s = line.strip()
    if not s or s.startswith("•") or RANGE_RE.match(s) or TIP_RE.match(s):
        return None
    if PARAM_COL_EXCLUDE_RE.search(s):
        return None
    parts = split_col_row(s)
    if not parts or not (2 <= len(parts) <= 6):
        return None
    if not all(is_param_col_cell(p) for p in parts):
        return None
    if any(p in ("L", "R", "V") for p in parts) and any(
        re.search(r"FX|Delay|Pre-Dist|Main|Echo|Regen|Flanger|Level|Shifter", p, re.I)
        for p in parts
    ):
        return None
    return parts


def render_param_col_grid(
    rows: list[list[str]], terms: dict[str, list[str]], fname: str
) -> str:
    ncols = len(rows[0])
    cls = f'param-cols cols-{ncols}' if ncols > 2 else "param-cols"
    parts = [f'<table class="{cls}"><tbody>']
    for row in rows:
        cells = row + [""] * (ncols - len(row))
        tds = "".join(
            f"<td>{apply_tags(c, terms, source_file=fname) if c else '&nbsp;'}</td>"
            for c in cells
        )
        parts.append(f"<tr>{tds}</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def consume_param_col_grid(
    lines: list[str], i: int, terms: dict[str, list[str]], fname: str
) -> tuple[str | None, int]:
    rows: list[list[str]] = []
    j = i
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            break
        parts = split_param_col_row(s)
        if not parts:
            break
        if rows and len(parts) != len(rows[0]):
            break
        rows.append(parts)
        j += 1
    if not rows:
        return None, i
    if len(rows) == 1 and len(rows[0]) < 3:
        return None, i
    return render_param_col_grid(rows, terms, fname), j


def is_data_col_cell(cell: str) -> bool:
    if not cell or len(cell) > 30:
        return False
    if re.fullmatch(r"[#OXox\d]+", cell):
        return True
    if NOT_HEADING_START.match(cell):
        return False
    if re.search(r"\b(the|this|when|will|page|parameter|uses normal|default setting)\b", cell, re.I):
        return False
    if cell.startswith("•"):
        return False
    return True


def split_data_col_row(line: str) -> list[str] | None:
    s = line.strip()
    if not s or s.startswith("•") or RANGE_RE.match(s) or TIP_RE.match(s):
        return None
    if PARAM_COL_EXCLUDE_RE.search(s):
        return None
    parts = split_col_row(s)
    if not parts or not (2 <= len(parts) <= 8):
        return None
    if not all(is_data_col_cell(p) for p in parts):
        return None
    return parts


def render_data_col_grid(
    rows: list[list[str]], terms: dict[str, list[str]], fname: str
) -> str:
    ncols = len(rows[0])
    parts = ['<table class="data-table lookup"><tbody>']
    for row in rows:
        cells = row + [""] * (ncols - len(row))
        tds = "".join(
            f"<td>{apply_tags(c, terms, source_file=fname) if c else '&nbsp;'}</td>"
            for c in cells
        )
        parts.append(f"<tr>{tds}</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


def consume_data_col_grid(
    lines: list[str], i: int, terms: dict[str, list[str]], fname: str
) -> tuple[str | None, int]:
    rows: list[list[str]] = []
    j = i
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            break
        parts = split_data_col_row(s)
        if not parts:
            break
        if rows and len(parts) != len(rows[0]):
            break
        rows.append(parts)
        j += 1
    if len(rows) < 3:
        return None, i
    return render_data_col_grid(rows, terms, fname), j


def render_bullet_grid(rows: list[list[str]], terms: dict[str, list[str]]) -> str:
    ncols = max(len(r) for r in rows)
    out = ['<table class="bullet-cols">']
    for row in rows:
        cells = list(row) + [""] * (ncols - len(row))
        tds = "".join(f"<td>{apply_tags(c, terms) if c else '&nbsp;'}</td>" for c in cells)
        out.append(f"<tr>{tds}</tr>")
    out.append("</table>")
    return "".join(out)


def consume_bullet_grid(
    lines: list[str], i: int, terms: dict[str, list[str]]
) -> tuple[str | None, int]:
    rows: list[list[str]] = []
    j = i
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            break
        parts = split_bullet_grid_row(s)
        if not parts:
            break
        rows.append(parts)
        j += 1
    if rows and j < len(lines):
        s = lines[j].strip()
        k = j + 1
        while k < len(lines) and not lines[k].strip():
            k += 1
        nxt = lines[k].strip() if k < len(lines) else ""
        if is_bullet_grid_orphan(s, nxt, rows):
            rows.append([s])
            j += 1
    if len(rows) < 2:
        return None, i
    return render_bullet_grid(rows, terms), j


def tidy_lookup_row(parts: list[str]) -> list[str]:
    """Drop an OCR extra digit in 0–99 value columns (865 → 86)."""
    out = list(parts)
    for i in range(0, len(out), 2):
        if re.fullmatch(r"\d{3}", out[i]) and 0 <= int(out[i][:2]) <= 99:
            out[i] = out[i][:2]
    return out


def merge_lookup_headers(header_rows: list[list[str]], ncols: int) -> list[str]:
    if not header_rows:
        return []
    if len(header_rows) >= 2:
        a, b = header_rows[0], header_rows[1]
        half = ncols // 2
        if len(a) == half and len(b) == ncols:
            out = []
            for i in range(half):
                out.append(b[2 * i].title() if b[2 * i].islower() else b[2 * i])
                unit = b[2 * i + 1] if 2 * i + 1 < len(b) else ""
                top = a[i] if i < len(a) else "time"
                out.append(f"{top} {unit}".strip())
            return [h[:1].upper() + h[1:] if h else h for h in out]
        if len(a) == half and len(b) == half:
            out = []
            for i in range(half):
                label = b[i]
                m = re.match(r"(?i)(value)\s*(\(.*\))?$", label)
                if m:
                    out.append(m.group(1).title())
                    unit = (m.group(2) or "").strip()
                    out.append(f"{a[i]} {unit}".strip() if unit else a[i])
                else:
                    out.append(label)
                    out.append(a[i])
            return [h[:1].upper() + h[1:] if h else h for h in out]
    flat: list[str] = []
    for row in header_rows:
        flat.extend(row)
    while len(flat) < ncols:
        flat.append("")
    return flat[:ncols]


def _five_empty(cells: list[str]) -> bool:
    return len(cells) >= 5 and all(not c for c in cells[:5])


def _five_full(cells: list[str]) -> bool:
    return len(cells) >= 5 and all(c for c in cells[:5])


def merge_leading_sparse(rows: list[list[str]]) -> list[list[str]]:
    """Join the opening BPM header/data pair into one 10-column row."""
    if len(rows) < 2:
        return rows
    a, b = rows[0], rows[1]
    if len(a) < 10 or len(b) < 10:
        return rows
    if _five_empty(a) and _five_full(a[5:]) and _five_full(b) and _five_empty(b[5:]):
        return [b[:5] + a[5:]] + rows[2:]
    if _five_full(a) and _five_empty(a[5:]) and _five_empty(b) and _five_full(b[5:]):
        return [a[:5] + b[5:]] + rows[2:]
    return rows


def normalize_delay_row(parts: list[str]) -> list[str] | None:
    """Turn a delay-chart line into 10 cells, or None to skip a header-only row."""
    if all(DELAY_LABEL_RE.match(p) for p in parts):
        return None
    if all(NUM_CELL_RE.match(p) for p in parts):
        if len(parts) == 5:
            return parts + [""] * 5
        return list(parts)
    if len(parts) >= 10:
        left, right = parts[:5], parts[5:10]
        left_hdr = all(DELAY_LABEL_RE.match(p) for p in left)
        right_hdr = all(DELAY_LABEL_RE.match(p) for p in right)
        left_num = all(NUM_CELL_RE.match(p) for p in left)
        right_num = all(NUM_CELL_RE.match(p) for p in right)
        if left_hdr and right_num:
            return [""] * 5 + right
        if left_num and right_hdr:
            return left + [""] * 5
    return None


def is_numeric_chart_line(line: str) -> bool:
    s = line.strip()
    return bool(
        numeric_header_cells(s)
        or delay_chart_parts(s)
        or numeric_lookup_cells(s)
    )


def collapse_paren_column(
    rows: list[list[str]], headers: list[str] | None
) -> tuple[list[list[str]], list[str] | None]:
    """Fold `(without FX)` into Will Select… when the printed header is 3-col."""
    if not rows or not headers or not headers[-1] == "":
        return rows, headers
    if not all(len(r) >= 2 and re.fullmatch(r"\([^)]*\)", r[-2]) for r in rows):
        return rows, headers
    merged = [r[:-2] + [f"{r[-2]} {r[-1]}".strip()] for r in rows]
    return merged, headers[:-1]


def render_data_table(
    rows: list[list[str]],
    terms: dict[str, list[str]],
    *,
    caption: str = "",
    headers: list[str] | None = None,
    lookup: bool = False,
) -> str:
    cls = "data-table lookup" if lookup else "data-table"
    tid = f' id="{slugify(caption)}"' if caption else ""
    parts = [f'<table class="{cls}"{tid}>']
    if caption:
        parts.append(f"<caption>{apply_tags(caption, terms, heading=True)}</caption>")
    if headers:
        ths = "".join(f"<th>{apply_tags(h, terms)}</th>" for h in headers)
        parts.append(f"<thead><tr>{ths}</tr></thead>")
    parts.append("<tbody>")
    for row in rows:
        tds = "".join(f"<td>{apply_tags(c, terms)}</td>" for c in row)
        parts.append(f"<tr>{tds}</tr>")
    parts.append("</tbody></table>")
    return "".join(parts)


EFFECTS_ALGO_INTRO_RE = re.compile(r"available effects algorithms are:\s*$", re.I)
EFFECTS_ALGO_ENTRY_RE = re.compile(r"^\d{1,2}\s+\S")
EFFECTS_ALGO_CONT_DIGIT_RE = re.compile(r"^\d$")
EFFECTS_ALGO_CONT_TAIL_RE = re.compile(r"^(\d+)\s+([A-Z]+)$")


def join_table_cols(parts: list[str]) -> str:
    return ("          ".join(p.strip() for p in parts if p.strip()))


def is_effects_algo_table_row(line: str) -> bool:
    s = line.strip()
    if not s or TIP_RE.match(s) or is_running_header(s):
        return False
    parts = split_cols(s)
    if len(parts) >= 3 and EFFECTS_ALGO_ENTRY_RE.match(parts[0]):
        return True
    if len(parts) >= 4 and EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(parts[0]):
        return True
    if len(parts) == 2 and all(EFFECTS_ALGO_ENTRY_RE.match(p) for p in parts):
        return True
    return False


def is_effects_algo_continuation(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(s):
        return True
    return bool(EFFECTS_ALGO_CONT_TAIL_RE.match(s))


def merge_effects_algo_continuation(prev: str, cont: str) -> str:
    cont = cont.strip()
    parts = split_cols(prev)
    if EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(cont):
        if len(parts) >= 4 and EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(parts[0]):
            parts = [f"{parts[0]}{cont} {parts[1]}"] + parts[2:]
        elif parts:
            m = re.match(r"^(\d)(\s+)(.*)$", parts[0])
            if m:
                parts[0] = f"{m.group(1)}{cont}{m.group(2)}{m.group(3)}"
            elif len(parts) >= 2 and EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(parts[0]):
                parts = [f"{parts[0]}{cont} {parts[1]}"] + parts[2:]
        return join_table_cols(parts)
    m = EFFECTS_ALGO_CONT_TAIL_RE.match(cont)
    if m and parts:
        if len(parts) >= 4 and EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(parts[0]):
            num = f"{parts[0]}{m.group(1)}"
            name = f"{parts[1]}{m.group(2)}"
            parts = [f"{num} {name}"] + parts[2:]
        else:
            m0 = re.match(r"^(\d+)(\s+)(.*)$", parts[0])
            if m0:
                parts[0] = f"{m0.group(1)}{m.group(1)}{m0.group(2)}{m0.group(3)}{m.group(2)}"
        return join_table_cols(parts)
    return prev


def effects_algo_row_cells(line: str) -> list[str]:
    parts = split_cols(line.strip())
    if len(parts) >= 4 and EFFECTS_ALGO_CONT_DIGIT_RE.fullmatch(parts[0]):
        parts = [f"{parts[0]} {parts[1]}"] + parts[2:]
    row = (parts + ["", "", ""])[:3]
    return row


def merge_effects_algo_lines(raw: list[str]) -> list[str]:
    merged: list[str] = []
    for line in raw:
        s = line.strip()
        if not s or is_running_header(s):
            continue
        if is_effects_algo_continuation(s):
            if merged:
                merged[-1] = merge_effects_algo_continuation(merged[-1], s)
            continue
        if PAGE_NUM_RE.match(s) and len(s) <= 3:
            continue
        if is_effects_algo_table_row(s):
            merged.append(s)
    return merged


def consume_effects_algorithm_table(
    lines: list[str], i: int, terms: dict[str, list[str]]
) -> tuple[str | None, int]:
    """Three-column effect algorithm list (Section 6 Selecting Effects)."""
    raw: list[str] = []
    j = i
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        if TIP_RE.match(s) or s.startswith("What is an Algorithm"):
            break
        if is_running_header(s):
            j += 1
            continue
        if is_effects_algo_continuation(s) or is_effects_algo_table_row(s):
            raw.append(s)
            j += 1
            continue
        if raw:
            break
        j += 1
    logical = merge_effects_algo_lines(raw)
    if len(logical) < 3:
        return None, i
    rows = [effects_algo_row_cells(line) for line in logical]
    return (
        render_data_table(
            rows,
            terms,
            caption="Effect Algorithms",
        ),
        j,
    )


def consume_numeric_table(
    lines: list[str], i: int, terms: dict[str, list[str]]
) -> tuple[str | None, int]:
    j = i
    caption = ""
    if is_lookup_caption(lines[j]):
        caption = lines[j].strip()
        j += 1
        while j < len(lines) and not lines[j].strip():
            j += 1
    headers: list[list[str]] = []
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            j += 1
            continue
        cells = numeric_header_cells(s)
        if not cells:
            break
        headers.append(cells)
        j += 1
    body: list[list[str]] = []
    delay = False
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            if k < len(lines) and is_numeric_chart_line(lines[k]):
                j += 1
                continue
            break
        delay_parts = delay_chart_parts(s)
        if delay_parts:
            delay = True
            row = normalize_delay_row(delay_parts)
            j += 1
            if row is not None:
                body.append(row)
            continue
        cells = numeric_lookup_cells(s)
        if not cells:
            break
        body.append(cells)
        j += 1
    if len(body) < 8:
        return None, i
    if delay:
        body = merge_leading_sparse(body)
        ncols = max(len(r) for r in body)
        body = [r + [""] * (ncols - len(r)) for r in body]
        groups = max(1, (ncols + 4) // 5)
        head = DELAY_HEADERS * groups
        head = head[:ncols] + [""] * max(0, ncols - len(head))
        if not caption:
            caption = "Delay Times/Tempo BPM Chart"
        return render_data_table(body, terms, caption=caption, headers=head[:ncols]), j
    if headers:
        body = [tidy_lookup_row(r) for r in body]
    ncols = max(len(r) for r in body)
    body = [r + [""] * (ncols - len(r)) for r in body]
    head = merge_lookup_headers(headers, ncols)
    return render_data_table(
        body, terms, caption=caption, headers=head or None, lookup=bool(head)
    ), j


def consume_matrix_table(
    lines: list[str], i: int, terms: dict[str, list[str]]
) -> tuple[str | None, int]:
    """YES/NO charts such as GLIDE MODES."""
    j = i
    caption = ""
    if is_lookup_caption(lines[j].strip()):
        caption = lines[j].strip()
        j += 1
        while j < len(lines) and not lines[j].strip():
            j += 1
    headers: list[list[str]] = []
    body: list[list[str]] = []
    while j < len(lines):
        s = lines[j].strip()
        if not s:
            k = j + 1
            while k < len(lines) and not lines[k].strip():
                k += 1
            nxt = lines[k].strip() if k < len(lines) else ""
            if (headers or body) and (
                is_yesno_row(nxt)
                or is_chart_header_row(nxt)
                or is_chart_paren_row(nxt)
                or (not body and is_header_wrap_atom(nxt))
            ):
                j += 1
                continue
            break
        if not body and (is_chart_header_row(s) or is_header_wrap_atom(s)):
            headers.append(split_cols(s) if is_chart_header_row(s) else [s])
            j += 1
            continue
        if is_chart_paren_row(s):
            if body:
                body[-1][0] = f"{body[-1][0]} {s}"
                j += 1
                continue
            break
        if is_yesno_row(s):
            body.append(split_cols(s))
            j += 1
            continue
        break
    if len(body) < 3:
        return None, i
    ncols = max(len(r) for r in body)
    body = [r + [""] * (ncols - len(r)) for r in body]
    head = merge_matrix_headers(headers, ncols)
    return render_data_table(
        body, terms, caption=caption, headers=head or None
    ), j


def looks_like_chart_rows(rows: list[list[str]]) -> bool:
    """Enough aligned columns that this is a printed chart, not VFD callouts."""
    if len(rows) < 3:
        return False
    widths = [len(r) for r in rows]
    wide = max(widths)
    return wide >= 3 and len(rows) >= 3 and widths.count(wide) >= 3


def render_chart_from_callouts(
    rows: list[list[str]], terms: dict[str, list[str]]
) -> str:
    ncols = max(len(r) for r in rows)
    padded = [r + [""] * (ncols - len(r)) for r in rows]
    first = padded[0]
    vals = [c for c in first if c]
    headerish = bool(vals) and all(
        not NUM_CELL_RE.match(c)
        and c.lower() not in ("yes", "no", "on", "off")
        and len(c) < 48
        and not c.endswith(".")
        for c in vals
    )
    if headerish:
        body, headers = collapse_paren_column(padded[1:], first)
        return render_data_table(body, terms, headers=headers)
    return render_data_table(padded, terms)


def table_row_ahead(lines: list[str], j: int) -> bool:
    """True if another name|description row follows, after optional wrap leftovers."""
    k = j + 1
    while k < len(lines):
        t = lines[k].strip()
        k += 1
        if not t:
            continue
        if split_twocol_row(t) or split_twocol_row(t, in_table=True):
            return True
        if RANGE_RE.match(t) or TIP_RE.match(t) or is_bullet_item(t) or is_param_heading(t):
            return False
        if toc_heading_kind(t) or is_prose_heading(t):
            return False
        if t.lower().startswith(("note:", "important:")) or looks_like_title(t):
            return False
        kind = classify(t)
        if kind in ("h1", "h2", "h3", "h4", "range", "tip", "algo", "vfd", "callouts"):
            return False
        if NOT_HEADING_START.match(t) and t[:1].isupper() and cell_complete(t):
            return False
    return False


def stack_callout_rows(rows: list[list[str]]) -> list[str]:
    cols = ["", "", ""]
    for row in rows:
        row = (row + ["", "", ""])[:3]
        for k, cell in enumerate(row):
            cols[k] = f"{cols[k]} {cell}".strip() if cols[k] else cell
    return cols


def callout_key(labels: list[str]) -> str:
    return "|".join(labels)


def render_callouts(labels: list[str], side: str, *, page: str = "") -> str:
    if not any(labels):
        return ""
    labs = list(labels)
    page_lab = ""
    if page:
        if len(labs) >= 4:
            page_lab, labs = labs[0], labs[1:4]
        spacer = (
            f"<div>{html.escape(page_lab)}</div>"
            if page_lab
            else '<div class="page-spacer"></div>'
        )
    else:
        spacer = ""
    cells = "".join(
        f"<div>{html.escape(lab)}</div>" if lab else "<div></div>"
        for lab in (labs + ["", "", ""])[:3]
    )
    cls = f"vfd-callouts {side}" + (" has-page" if page else "")
    return f'<div class="{cls}">{spacer}{cells}</div>'


def index_set(val) -> set[int]:
    if isinstance(val, list):
        return {int(x) for x in val if int(x) >= 0}
    if isinstance(val, int) and val >= 0:
        return {val}
    return set()


def vfd_cells(
    values: list[str],
    selected: int | list[int] = -1,
    layered: int | list[int] | None = None,
) -> str:
    out = []
    sel = index_set(selected)
    lay = index_set(layered)
    for i, p in enumerate((values + ["", "", ""])[:3]):
        text = "".join(c for c in p.upper() if c in VFD_ALLOWED)
        classes = ["cell"]
        if i in sel:
            classes.append("selected")
        if i in lay:
            classes.append("flash-underline")
            inner = f"<span>{html.escape(text)}</span>" if text else "&nbsp;"
        else:
            inner = html.escape(text) if text else "&nbsp;"
        out.append(f'<td class="{" ".join(classes)}">{inner}</td>')
    return "".join(out)


def page_label_cell(page: str, *, empty: bool = False, status: str = "") -> str:
    if not page and not status:
        return ""
    if empty:
        if status:
            text = "".join(c for c in status.upper() if c in VFD_ALLOWED)
            inner = html.escape(text)
            if status.upper() == "SAVE":
                inner = f'<span class="classic-blink">{inner}</span>'
            return f'<td class="cell page-label">{inner}</td>'
        return '<td class="cell page-label">&nbsp;</td>'
    text = "".join(c for c in page.upper() if c in VFD_ALLOWED)
    return f'<td class="cell page-label">{html.escape(text)}</td>'


def skip_screen_leftovers(lines: list[str], i: int, screen: dict) -> int:
    """Drop OCR leftovers that sat in the PDF figure after a harvested mockup."""
    until = screen.get("skip_until")

    def hits_until(s: str) -> bool:
        if not until:
            return False
        t = re.sub(r"\s+", " ", s.lstrip("• ").strip())
        u = re.sub(r"\s+", " ", until.strip())
        return t.startswith(u)

    while i < len(lines):
        s = lines[i].strip()
        if hits_until(s):
            break
        if not s or is_figure_label_row(lines[i]) or classify(lines[i]) == "callouts" or is_partial_callout(s):
            i += 1
            continue
        if until:
            kind = classify(lines[i])
            if kind in ("h1", "h2", "h3", "h4", "range", "tip", "algo"):
                break
            if kind == "p" and len(s) > 80:
                break
            i += 1
            continue
        break
    return i


def render_vfd_screen(
    screen: dict,
    *,
    callouts_top: list[str] | None = None,
    callouts_bottom: list[str] | None = None,
    selected: int = -1,
    caption: str = "",
) -> str:
    rows = screen.get("rows") or [["", "", ""], ["", "", ""]]
    top = list(rows[0] if rows else ["", "", ""])
    bottom = list(rows[1] if len(rows) > 1 else ["", "", ""])
    while len(top) < 3:
        top.append("")
    while len(bottom) < 3:
        bottom.append("")
    if not any(top) and not any(bottom):
        return ""
    if not callouts_top:
        callouts_top = screen.get("callouts_top")
    if not callouts_bottom:
        callouts_bottom = screen.get("callouts_bottom")
    page = screen.get("page", "")
    status = screen.get("status", "")
    has_page = bool(page or status)
    sel_set = index_set(screen.get("selected", selected))
    lay_set = index_set(screen.get("layered"))
    empty_th = '<th class="page-tag-slot"></th>' if has_page else ""
    cols = (
        '<col class="page-col"><col class="param-col"><col class="param-col"><col class="param-col">'
        if has_page
        else '<col class="param-col"><col class="param-col"><col class="param-col">'
    )
    unit_cls = "vfd-unit has-page" if has_page else "vfd-unit"
    pressed = lambda n: " pressed" if n in sel_set else ""
    aria = lambda n: ' aria-pressed="true"' if n in sel_set else ""
    cap = caption or screen.get("caption") or ""
    if cap:
        cap = f"<figcaption>{apply_tags(cap, load_terms())}</figcaption>"
    else:
        cap = ""
    return f"""<figure class="{unit_cls}">
  {render_callouts(callouts_top or [], "top", page=page or status)}
  <div class="vfd-bezel">
  <table>
    <colgroup>{cols}</colgroup>
    <thead>
      <tr class="soft-row top">
        {empty_th}
        <th><button type="button" class="soft-btn{pressed(0)}" data-pos="tl" aria-label="Top left soft button"{aria(0)}></button></th>
        <th><button type="button" class="soft-btn{pressed(1)}" data-pos="tc" aria-label="Top center soft button"{aria(1)}></button></th>
        <th><button type="button" class="soft-btn{pressed(2)}" data-pos="tr" aria-label="Top right soft button"{aria(2)}></button></th>
      </tr>
    </thead>
    <tbody class="vfd-screen">
      <tr>{page_label_cell(page, status=status)}{vfd_cells(top, [i for i in sel_set if i < 3], [i for i in lay_set if i < 3])}</tr>
      <tr>{page_label_cell(page or status, empty=True, status=status)}{vfd_cells(bottom, [i - 3 for i in sel_set if i >= 3], [i - 3 for i in lay_set if i >= 3])}</tr>
    </tbody>
    <tfoot>
      <tr class="soft-row bottom">
        {empty_th}
        <td><button type="button" class="soft-btn{pressed(3)}" data-pos="bl" aria-label="Bottom left soft button"{aria(3)}></button></td>
        <td><button type="button" class="soft-btn{pressed(4)}" data-pos="bc" aria-label="Bottom center soft button"{aria(4)}></button></td>
        <td><button type="button" class="soft-btn{pressed(5)}" data-pos="br" aria-label="Bottom right soft button"{aria(5)}></button></td>
      </tr>
    </tfoot>
  </table>
  </div>
  {render_callouts(callouts_bottom or [], "bottom", page=page or status)}
  {cap}
</figure>"""


def vfd_unit(line: str, selected: int = 0) -> str:
    if any(c.islower() for c in line):
        return ""
    if is_multicolumn(line):
        parts = split_cols(line)
        while len(parts) < 6:
            parts.append("")
        parts = [p.upper() for p in parts[:6]]
        if not any(parts):
            return ""
        return render_vfd_screen({"page": "", "rows": [parts[:3], parts[3:6]]})
    parts = VFD_EQ_RE.findall(line)
    if len(parts) < 2:
        return ""
    while len(parts) < 6:
        parts.append("")
    parts = [p.upper()[:13] for p in parts[:6]]
    if not any(parts):
        return ""
    return render_vfd_screen(
        {"page": "", "rows": [parts[:3], parts[3:6]]},
        selected=selected,
    )


def load_terms() -> dict[str, list[str]]:
    return json.loads(TERMS_PATH.read_text())


BANKSET_WORD_RE = re.compile(r"(?<![\w>])(Bank[Ss]ets?)(?![\w<])")
BANKSET_ID_AFTER_RE = re.compile(
    r"^\s*(?:\()?(?:U[01]|R[1-4]|S[89]|[89](?!\d))",
    re.I,
)
BANKSET_BUTTON_AFTER_RE = re.compile(r"^\s+buttons?\b", re.I)
BANKSET_CONTROL_LIST_RE = re.compile(
    r"^(?:,\s*Bank\b|\s+and Bank\b).{0,40}\bbuttons?\b",
    re.I | re.S,
)
# Panel names tagged as kbd when the sentence is about using the control.
# Cue words: press/hold/click/double-click, or the word button nearby.
# Short labels like Sounds or Wave must not be tagged in every mention.
PRESS_VERB_RE = re.compile(
    r"\b(?:(?:rapidly\s+)?double-click(?:s|ing)?|press(?:es|ing|ed)?|"
    r"hold(?:ing|s)?|held|click(?:s|ing)?)\b",
    re.I,
)
BUTTON_WORD_RE = re.compile(r"\bbuttons?\b", re.I)
BUTTON_WORD_AFTER_RE = re.compile(
    r"^\.?(?:\s+\([^)]{0,40}\))?\s+buttons?\b",
    re.I,
)
BUTTON_IS_PRESSED_AFTER_RE = re.compile(
    r"^\s+button\s+is\s+(?:pressed|held)\b",
    re.I,
)
PRESS_IMMEDIATE_RE = re.compile(
    r"\b(?:(?:rapidly\s+)?double-click(?:s|ing)?|press(?:es|ing|ed)?|"
    r"hold(?:ing|s)?|held|click(?:s|ing)?)"
    r"(?:\s+down)?"
    r"(?:\s+\([^)]{0,80}\))?"
    r"(?:\s+(?:any|one|each)(?:\s+of)?)?"
    r"(?:\s+the)?"
    r"\s+$",
    re.I,
)
LIST_FILLER_RE = re.compile(
    r"\b(?:and/or|and|or|the|a|an|one|any|each|of|such as|like|"
    r"including|namely|e\.g\.|eg|for example|then|buttons?)\b",
    re.I,
)
PANEL_BUTTON_EXTRAS = [
    "Mix•Pan",
    "Mix-Pan",
    "Up/Down Arrow",
    "Up Arrow",
    "Down Arrow",
    "Left Arrow",
    "Right Arrow",
    "Left/Right Cursor",
    "MIDI Control",
    "Sequencer Locate",
    "Sequencer Click",
    "Seq/Song Tracks 1-6",
    "Seq/Song Tracks 7-12",
    "Seq/Song Tracks",
    "Track MIDI",
    "Edit Song",
    "Edit Sequence",
    "Edit Track",
    "Pitch Mods",
    "Program Control",
    "Performance Options",
    "Mod Mixer",
    "Env 3",
    "Env 2",
    "Env 1",
    "Wave",
    "Pitch",
    "Output",
    "Filters",
    "LFO",
    "Record",
    "Stop•Continue",
    "Stop/Continue",
    "Copy",
    "Click",
    "Locate",
    "Storage",
    "Sounds",
    "Presets",
    "System",
    "MIDI",
    "Compare",
    "Seq Control",
    "Sequencer Control",
    "Attack/Release",
    "Brightness/Timbre",
    "Key Zone/Velocity",
    "Tuning",
    "Controllers On/Off",
    "Play",
    "Layer (Program Control)",
    "Seq/Song Tracks 1-6 (or 7-12)",
    "Seq/Song Tracks 1-6 or 7-12",
    "Seq/Song Tracks 1-6 and/or 7-12",
    "Seq/Song Track 1-6 and/or 7-12",
    "Seq/Song Track 1-6",
    "Seq/Song Track 7-12",
    "Tracks 1-6 or 7-12",
    "Record/Play",
    "Track/MIDI",
    "Sequence Control",
    "Bank 0-9",
    "Bank 0–9",
    "Preset",
    "Bank",
] + [f"Bank {i}" for i in range(10)]


def wrap_bankset(escaped: str) -> str:
    """Tag BankSet as kbd.button only for the panel control, not the memory set.

    Button: the word button after the name, a press/click verb immediately
    before it, or “BankSet and Bank buttons”. Term: BankSet U0 / R2 / S8 / 8,
    plurals, and every other mention.
    """

    def repl(m: re.Match[str]) -> str:
        word = m.group(1)
        after = escaped[m.end() :]
        before = re.sub(r"<[^>]+>", "", escaped[max(0, m.start() - 72) : m.start()])
        if word.lower().endswith("s"):
            return f'<dfn class="term">{word}</dfn>'
        if BANKSET_ID_AFTER_RE.match(after):
            return f'<dfn class="term">{word}</dfn>'
        if BANKSET_BUTTON_AFTER_RE.match(after):
            return f'<kbd class="button">{word}</kbd>'
        if BANKSET_CONTROL_LIST_RE.match(after):
            return f'<kbd class="button">{word}</kbd>'
        if PRESS_IMMEDIATE_RE.search(before):
            return f'<kbd class="button">{word}</kbd>'
        return f'<dfn class="term">{word}</dfn>'

    return BANKSET_WORD_RE.sub(repl, escaped)


def panel_button_names(terms: dict[str, list[str]]) -> list[str]:
    names = [n for n in terms.get("button", []) if n.lower() not in {"bankset", "banksets"}]
    names.extend(PANEL_BUTTON_EXTRAS)
    seen: set[str] = set()
    out: list[str] = []
    for name in sorted(names, key=len, reverse=True):
        key = name.lower()
        if key in seen or len(name) < 3:
            continue
        seen.add(key)
        out.append(name)
    return out


def _only_panel_names(fragment: str, names_longest: list[str]) -> bool:
    """True when fragment is only known panel names and list filler."""
    text = re.sub(r"<[^>]+>", " ", fragment)
    text = LIST_FILLER_RE.sub(" ", text)
    text = re.sub(r"[\s,;:—–]+", " ", text).strip().lower()
    if not text:
        return True
    while text:
        hit = next((n for n in names_longest if text == n or text.startswith(n + " ")), None)
        if hit is None:
            return False
        text = text[len(hit) :].strip()
    return True


def _tail_after_last(pattern: re.Pattern[str], before: str) -> str | None:
    last = None
    for last in pattern.finditer(before):
        pass
    if last is None:
        return None
    tail = before[last.end() :]
    if re.search(r"[.!?]", tail):
        return None
    return tail


def wrap_press_buttons(escaped: str, names: list[str]) -> str:
    """Tag panel labels as kbd.button next to press/click or the word button."""

    names_longest = [n.lower() for n in names]

    for name in names:
        pat = re.compile(rf"(?<![\w>/])({re.escape(html.escape(name))})(?![\w</-])")

        def repl(m: re.Match[str], text: str = escaped) -> str:
            word = m.group(1)
            before_raw = text[max(0, m.start() - 220) : m.start()]
            before = re.sub(r"<[^>]+>", "", before_raw)
            after = text[m.end() : m.end() + 80]
            if re.search(r"<[a-z][^>]*>[^<]*$", before_raw, re.I):
                return word
            if BUTTON_WORD_AFTER_RE.match(after) or BUTTON_IS_PRESSED_AFTER_RE.match(after):
                return f'<kbd class="button">{word}</kbd>'
            if PRESS_IMMEDIATE_RE.search(before):
                return f'<kbd class="button">{word}</kbd>'
            press_tail = _tail_after_last(PRESS_VERB_RE, before)
            if press_tail is not None and _only_panel_names(press_tail, names_longest):
                return f'<kbd class="button">{word}</kbd>'
            btn_tail = _tail_after_last(BUTTON_WORD_RE, before)
            if btn_tail is not None and _only_panel_names(btn_tail, names_longest):
                return f'<kbd class="button">{word}</kbd>'
            btn = BUTTON_WORD_RE.search(after)
            if btn and not re.search(r"[.!?]", after[: btn.start()]):
                if _only_panel_names(after[: btn.start()], names_longest):
                    return f'<kbd class="button">{word}</kbd>'
            return word

        escaped = pat.sub(repl, escaped)
    return escaped


PAGE_NAME_BLOCK_PREFIX = re.compile(
    r"^(?:This|That|The|Next|Previous|Following|Same|Last|First|Second|Third|Another|Each|Every|Any|Either|Current|New|Prior|Own|One|Other|Accessible|Active|Entire|Whole|Printed|Top level|Rest of the|Diagram on the following|Velocity response curves are shown on the next|MIDI Implementation Chart on the next|Power-on showing the last|Using the|Returning to the|Quick Way to get to the|Repeatedly pressing the same|Layering Sounds on The Tracks|About the Audition|Current Event|For each|Discussion of|Selecting INFO|Pressing EDIT|Pressing the soft button above|As you have no doubt noticed, the TS-10 displays exactly the same)\b",
    re.I,
)
PAGE_NAME_PROSE_RE = re.compile(
    r"\b(?:on the|on next|on this|or the|as described|begins on|displays|displayed|function on|parameter on|parameters on|values on|command on|controller on|returns with|returned to|shows the|showing the|reveals the|reveal the following|exactly the same|where the|which way you|regardless of which|any time this|editor page|song step editor|event editor|following sub|mode and return|and return to)\b",
    re.I,
)
PAGE_NAME_ON_THE_RE = re.compile(
    r"\b(?:on|from|to|at|into)\s+the\s+([A-Z0-9][A-Za-z0-9/+ -]{1,40}?)\s+(Page|page|Sub-Page|Sub-page|sub-page)\b(?![\w<])"
)
PAGE_NAME_INLINE_RE = re.compile(
    r"(?<![\w>])([A-Z0-9][A-Za-z0-9/+ -]{1,44}?)\s+(Page|page|Sub-Page|Sub-page|sub-page)\b(?![\w<])"
)
PAGE_SUFFIX_RE = re.compile(r"\s+(?:Page|page|Sub-Page|Sub-page|sub-page)\b")


def wrap_page_names(escaped: str, terms: dict[str, list[str]]) -> str:
    """Tag inline UI page references as span.page-name."""
    del terms  # registry lives in notes/terms.json; matching is pattern-based.

    def accept(name: str) -> bool:
        name = name.strip(" ,-")
        if len(name) < 2 or len(name) > 44:
            return False
        if PAGE_NAME_BLOCK_PREFIX.match(name):
            return False
        if PAGE_NAME_PROSE_RE.search(name):
            return False
        if re.search(
            r"\b(is|are|was|will|can|have|from|with|when|you|see|consult|same|exactly|repeatedly|pressing|using|returning|quick)\b",
            name,
            re.I,
        ):
            return False
        if name.lower() in {"section", "parameter", "parameters", "control", "effect parameter"}:
            return False
        if re.search(r"\b(this|that)\b", name, re.I):
            return False
        if name.lower().startswith("on ") or name.lower().endswith(" the"):
            return False
        return bool(re.match(r"^[A-Z0-9]", name))

    def tag(name: str, suffix: str) -> str:
        name = name.strip(" ,-")
        if not accept(name):
            return f"{name} {suffix}"
        return f'<span class="page-name">{name} {suffix}</span>'

    def repl_on_the(m: re.Match[str]) -> str:
        return tag(m.group(1), m.group(2))

    def repl_inline(m: re.Match[str]) -> str:
        return tag(m.group(1), m.group(2))

    parts = re.split(r"(<[^>]+>)", escaped)
    in_page_name = False
    for i, part in enumerate(parts):
        if part.startswith("<"):
            in_page_name = 'class="page-name"' in part
            continue
        if in_page_name:
            in_page_name = False
            continue
        part = PAGE_NAME_ON_THE_RE.sub(repl_on_the, part)
        parts[i] = PAGE_NAME_INLINE_RE.sub(repl_inline, part)
    return "".join(parts)


def apply_tags(
    text: str,
    terms: dict[str, list[str]],
    *,
    heading: bool = False,
    source_file: str | None = None,
) -> str:
    escaped = html.escape(text)
    escaped = link_section_refs(escaped, source_file)
    if heading:
        escaped = wrap_press_buttons(escaped, panel_button_names(terms))
        escaped = wrap_bankset(escaped)
        if not PAGE_TITLE_RE.match(text.strip()):
            escaped = wrap_page_names(escaped, terms)
        return link_chart_refs(escaped)

    def wrap(items: list[str], cls: str, tag: str = "span", *, skip_page_suffix: bool = False) -> None:
        nonlocal escaped
        for item in sorted(items, key=len, reverse=True):
            if len(item) < 3:
                continue
            item_esc = re.escape(html.escape(item))
            if skip_page_suffix:
                tail = rf"(?!{PAGE_SUFFIX_RE.pattern})(?![\w<])"
            else:
                tail = r"(?![\w<])"
            pat = re.compile(rf"(?<![\w>])({item_esc}){tail}")
            if cls == "button":
                escaped = pat.sub(r'<kbd class="button">\1</kbd>', escaped)
            elif cls == "term":
                escaped = pat.sub(r'<dfn class="term">\1</dfn>', escaped)
            else:
                escaped = pat.sub(rf'<{tag} class="{cls}">\1</{tag}>', escaped)

    if not heading:
        def wrap_eq(match: re.Match[str]) -> str:
            s = match.group(0)
            if s.endswith("-"):
                return s
            trail = ""
            if s.endswith("."):
                s, trail = s[:-1], "."
            return f'<span class="lcd">{s}</span>{trail}'

        escaped = VFD_EQ_RE.sub(wrap_eq, escaped)

        def wrap_in_text(pattern: re.Pattern[str], repl) -> None:
            nonlocal escaped
            parts = re.split(r"(<[^>]+>)", escaped)
            skip_text = False
            for i, part in enumerate(parts):
                if part.startswith("<"):
                    skip_text = part.startswith('<span class="lcd">')
                    continue
                if skip_text:
                    skip_text = False
                    continue
                parts[i] = pattern.sub(repl, part)
            escaped = "".join(parts)

        wrap_in_text(LCD_STAR_RE, lambda m: f'<span class="lcd">{m.group(0)}</span>')
        escaped = wrap_press_buttons(escaped, panel_button_names(terms))
        field_pat = re.compile(
            r"(?<![\w>])(" + "|".join(re.escape(x) for x in sorted(LCD_FIELDS, key=len, reverse=True)) + r")(?![\w<])"
        )
        wrap_in_text(field_pat, lambda m: f'<span class="lcd">{m.group(1)}</span>')
    wrap(terms.get("page", []), "page-name")
    escaped = wrap_page_names(escaped, terms)
    wrap(terms.get("function", []), "function", skip_page_suffix=True)
    wrap(["Seqs/Songs", "Replace Track Sound", "Track Effects", "Select Voice",
          "Write Program", "Program Effects", "Patch Select",
          "Data Entry Slider", "Volume Slider"], "button", skip_page_suffix=True)
    escaped = wrap_bankset(escaped)
    wrap(terms.get("term", []), "term")
    if source_file and source_file.startswith("07-effects-") and EFFECT_PARAM_NAMES:
        wrap(EFFECT_PARAM_NAMES, "param")
    wrap(terms.get("param", []), "param")
    wrap(terms.get("value", []), "value")
    wrap(["Sounds Mode", "Presets Mode", "Sequencer Mode", "General MIDI",
          "Group Edit", "Mono A", "Mono B"], "mode")
    escaped = link_effect_algo_refs(escaped, source_file)
    return link_chart_refs(escaped)


def button_float(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    img = ROOT / "references/buttons" / f"{slug}.png"
    if img.exists():
        inner = f'<img src="../references/buttons/{html.escape(img.name)}" alt="">'
    else:
        inner = '<span class="keycap-fallback" aria-hidden="true"></span>'
    return (
        f'<aside class="button-float"><table class="button-id"><tr><td>'
        f"{inner}<div class=\"button-label\">{html.escape(name)}</div>"
        f"</td></tr></table></aside>"
    )


PITCH_SHIFTER_DELAY_INTRO_RE = re.compile(
    r"^PITCH\s+SHIFTER \+ DELAY combines"
)
PITCH_SHIFTER_DELAY_PARAMS_RE = re.compile(r"^VOICE-1 SEMI\s+Range:")

VCF_DISTORTION_VCF_ROUTING_RE = re.compile(
    r"^VCF- -DISTORTION- -VCF Signal Routing$"
)
VCF_DISTORTION_VCF_PARAMS_RE = re.compile(r"^DIST LEVEL - IN\s+Range:")
VCF_DISTORTION_VCF_MIX_PROSE_RE = re.compile(
    r"^(The EFFECT MIX|Dry/Wet mixes\.)"
)


def consume_vcf_distortion_vcf_routing(
    lines: list[str],
    i: int,
    terms: dict[str, list[str]],
    fname: str,
) -> tuple[str | None, int]:
    """Algo 66: routing figure; skip diagram OCR; keep Dry/Wet mix prose."""
    if fname != "07-effects-60-73.html":
        return None, i
    if not VCF_DISTORTION_VCF_ROUTING_RE.match(lines[i].strip()):
        return None, i
    parts: list[str] = []
    src = "vcf-distortion-vcf-routing.png"
    alt = (
        "VCF- -DISTORTION- -VCF signal routing: FX-1 and FX-2 left/right inputs "
        "summed to mono through Variable HiPass Filter and Pre-Dist VCF (Env Fol); "
        "Distortion Level In, Clip, and Level Out with Bypass switch; Post-Dist "
        "VCF (Env Fol) to Main Outputs L and R"
    )
    caption = "VCF- -DISTORTION- -VCF signal routing."
    if (IMAGES / src).exists():
        parts.append(
            f'<figure class="figure"><img src="images/{html.escape(src)}" '
            f'alt="{html.escape(alt)}">'
            f"<figcaption>{apply_tags(caption, terms)}</figcaption></figure>"
        )
    j = i + 1
    while j < len(lines):
        s = lines[j].strip()
        if VCF_DISTORTION_VCF_PARAMS_RE.match(s):
            break
        if VCF_DISTORTION_VCF_MIX_PROSE_RE.match(s):
            parts.append(f"<p>{apply_tags(s, terms, source_file=fname)}</p>")
            j += 1
            continue
        j += 1
    return "\n".join(parts), j


def consume_pitch_shifter_delay_block(
    lines: list[str],
    i: int,
    terms: dict[str, list[str]],
    fname: str,
) -> tuple[str | None, int]:
    """Algo 59: intro prose (OCR table row) + routing figure, skip diagram OCR."""
    if fname != "07-effects-41-59.html":
        return None, i
    s = lines[i].strip()
    if not PITCH_SHIFTER_DELAY_INTRO_RE.match(s):
        return None, i
    intro = re.sub(
        r"^PITCH\s+SHIFTER \+ DELAY\s+",
        "PITCH SHIFTER + DELAY ",
        s,
    )
    parts = [f"<p>{apply_tags(intro, terms, source_file=fname)}</p>"]
    src = "pitch-shifter-delay-routing.png"
    alt = (
        "PITCH SHIFTER + DELAY signal routing: FX-1 and FX-2 left/right inputs "
        "summed and cross-fed to Vc 1 and Vc 2 stereo shifters with Regen "
        "feedback; delay mixer combines shifter outputs and Dry Level; panned "
        "shifter outputs and Delay Mix to Main Outputs L and R"
    )
    caption = "PITCH SHIFTER + DELAY signal routing."
    if (IMAGES / src).exists():
        parts.append(
            f'<figure class="figure"><img src="images/{html.escape(src)}" '
            f'alt="{html.escape(alt)}">'
            f"<figcaption>{apply_tags(caption, terms)}</figcaption></figure>"
        )
    j = i + 1
    while j < len(lines):
        if PITCH_SHIFTER_DELAY_PARAMS_RE.match(lines[j].strip()):
            break
        j += 1
    return "\n".join(parts), j


def consume_inline_figure(
    line: str, lines: list[str], i: int, chunks: list[str]
) -> int | None:
    """Insert a harvested PDF figure after this line and skip OCR leftovers."""
    inline = next((spec for spec in INLINE_FIGURES if spec["after"].search(line)), None)
    if not inline:
        return None
    src = inline.get("src")
    if src and (IMAGES / src).exists():
        chunks.append(
            f'<figure class="figure"><img src="images/{html.escape(src)}" '
            f'alt="{html.escape(inline["alt"])}">'
            f"<figcaption>{apply_tags(inline['caption'], load_terms())}</figcaption></figure>"
        )
    i += 1
    until = inline.get("skip_until")
    skip = inline.get("skip")
    while i < len(lines):
        s = lines[i].strip()
        if until and until.search(s):
            break
        if not s or (skip and skip.search(s)) or until:
            i += 1
            continue
        break
    return i


def looks_like_memory_map(line: str) -> bool:
    s = line.strip()
    if s == "ROM:":
        return True
    parts = split_cols(s)
    labels = {re.sub(r":$", "", p) for p in parts}
    return "User RAM" in labels and ("ROM" in labels or "BankSet R2" in labels)


def render_memory_map(terms: dict[str, list[str]]) -> str:
    """Three side-by-side Sound Memory tables (User RAM / ROM / Sampled Sounds)."""
    cols = [
        (
            "User RAM",
            [
                ("BankSet U0", "60 Programs", "60 Presets"),
                ("BankSet U1", "60 Programs", "60 Presets"),
            ],
            "Sounds and Presets stored in User RAM Memory can be played, edited, "
            "and replaced with other sounds or presets.",
        ),
        (
            "ROM",
            [
                ("BankSet R2", "60 Programs", "60 Presets"),
                ("BankSet R3", "60 Programs", "60 Presets"),
                ("BankSet R4", "60 Programs", "60 Presets"),
            ],
            "Sounds and Presets stored in the ROM Memory locations can be played "
            "and edited, but cannot be erased. Edited versions can be stored in User RAM.",
        ),
        (
            "Sampled Sounds",
            [
                ("BankSet S8", "10 Sampled Sound Banks (from the factory)",),
                ("BankSet S9", "10 Sampled Sound Banks (requires expansion SIMMs)",),
            ],
            "Sampled Sounds are stored in Dynamic RAM, and will not be saved "
            "internally when the TS-10 is turned off.",
        ),
    ]
    parts = ['<div class="memory-map">']
    for title, rows, note in cols:
        parts.append('<div class="memory-col">')
        parts.append(f'<table class="data-table"><caption>{html.escape(title)}</caption><tbody>')
        for row in rows:
            tds = "".join(f"<td>{apply_tags(c, terms)}</td>" for c in row)
            parts.append(f"<tr>{tds}</tr>")
        parts.append(f"</tbody></table><p class=\"memory-note\">{apply_tags(note, terms)}</p></div>")
    parts.append("</div>")
    return "".join(parts)


PRESET_ANATOMY_PARAMS = [
    "Mix",
    "Pan & Pan Mode",
    "Attack*",
    "Release*",
    "Brightness*",
    "Timbre*",
    "External MIDI Control (XCTRL)*",
    "Key Zone",
    "Velocity Range",
    "Velocity Sensitivity",
    "Transpose",
    "Detune",
    "Rate* (LFO and/or Wave-List Duration)",
    "Sustain On/Off",
    "Sostenuto On/Off",
    "Pitch Bend On/Off",
    "Mod Wheel On/Off",
    "Reset Controllers On/Off",
    "All-Notes-Off On/Off",
    "Patch Select mode*",
    "Pressure mode*",
    "Volume Pedal Mode",
    "MIDI Status",
    "MIDI Channel",
    "MIDI Program",
    "MIDI BankSelect",
    "Effects Bus Routing",
    "Effect Mod Control",
]


def looks_like_preset_anatomy(line: str) -> bool:
    return "The illustration below shows the relationship of the preset" in line


def render_preset_anatomy(catalog: dict, terms: dict[str, list[str]]) -> str:
    """Preset Effect diagram: hierarchy table, PSET LCD, Track Parameters list."""
    screen = catalog.get("screens", {}).get("preset-context") or {}
    tracks = "".join(
        f"<th>Track {n}</th>" for n in (1, 2, 3)
    )
    cells = "".join(
        "<td><ul><li>Sound</li><li>Track parameters</li></ul></td>" for _ in range(3)
    )
    params = "".join(
        f"<tr><td>{apply_tags(item, terms)}</td></tr>" for item in PRESET_ANATOMY_PARAMS
    )
    note = apply_tags("(* indicates saved with Programs)", terms)
    return (
        '<div class="preset-anatomy">'
        '<div class="preset-effect-main">'
        '<table class="data-table">'
        "<caption>Preset Effect</caption>"
        "<thead>"
        '<tr><th colspan="3">The Preset Effect Algorithm and its related parameters</th></tr>'
        f"<tr>{tracks}</tr>"
        "</thead>"
        f"<tbody><tr>{cells}</tr></tbody>"
        "</table>"
        f"{render_vfd_screen(screen)}"
        "</div>"
        '<div class="track-param-list">'
        '<table class="data-table">'
        "<caption>Track Parameters</caption>"
        f"<tbody>{params}</tbody>"
        "</table>"
        f'<p class="memory-note">{note}</p>'
        "</div></div>"
    )


DIAGRAM_CRUMBS = {
    "ENSONIQ",
    "CVP-1",
    "Control Voltage Foot Pedal",
    "Patch Select",
    "Buttons",
    "Pitch Bend",
    "Modulation",
    "Wheel",
}


def is_diagram_crumb(s: str) -> bool:
    t = s.strip()
    if t in DIAGRAM_CRUMBS:
        return True
    if re.fullmatch(r"\d{1,2}", t):
        return True
    if re.fullmatch(r"(?:\d{1,2}\s+){2,}\d{1,2}", t):
        return True
    return False


def to_html_body(
    lines: list[str],
    terms: dict[str, list[str]],
    fname: str,
    catalog: dict,
) -> str:
    chunks: list[str] = []
    used_button = False
    last_sid: str | None = None
    trigger_used: dict[str, int] = {}
    i = 0

    def tags(text: str, *, heading: bool = False) -> str:
        return apply_tags(text, terms, heading=heading, source_file=fname)

    while i < len(lines):
        line = lines[i]
        kind = classify(line)
        if kind == "blank" or is_diagram_crumb(line):
            i += 1
            continue
        ref_html, ref_i = consume_effect_param_ref_table(lines, i, terms, fname)
        if ref_html:
            chunks.append(ref_html)
            i = ref_i
            continue
        grid_html, ni = consume_param_col_grid(lines, i, terms, fname)
        if grid_html:
            chunks.append(grid_html)
            i = ni
            continue
        grid_html, ni = consume_data_col_grid(lines, i, terms, fname)
        if grid_html:
            chunks.append(grid_html)
            i = ni
            continue
        if looks_like_memory_map(line):
            chunks.append(render_memory_map(terms))
            while i < len(lines) and lines[i].strip() != "Using the BankSet Button":
                i += 1
            continue
        if looks_like_preset_anatomy(line):
            tagged = tags(line)
            chunks.append(f"<p>{tagged}</p>")
            chunks.append(render_preset_anatomy(catalog, terms))
            i += 1
            while i < len(lines) and not lines[i].strip().startswith(
                "Whenever the Presets LED"
            ):
                i += 1
            continue
        if kind == "callouts":
            ni = consume_inline_figure(line, lines, i, chunks)
            if ni is not None:
                i = ni
                continue
            rows, i = consume_callout_rows(lines, i)
            if looks_like_chart_rows(rows):
                chunks.append(render_chart_from_callouts(rows, terms))
                continue
            labels = stack_callout_rows(rows)
            sid = last_sid or catalog.get("by_callouts", {}).get(callout_key(labels))
            screen = catalog.get("screens", {}).get(sid) if sid else None
            bottom: list[str] | None = None
            j = i
            while j < len(lines) and not lines[j].strip():
                j += 1
            if screen and j < len(lines) and (
                classify(lines[j]) == "callouts" or is_partial_callout(lines[j])
            ):
                brows, i = consume_callout_rows(lines, j)
                bottom = stack_callout_rows(brows)
            if screen:
                edge = screen.get("callout_edge", "top")
                top_labs = labels if edge != "bottom" or bottom else None
                bot_labs = bottom if bottom else (labels if edge == "bottom" else None)
                chunks.append(
                    render_vfd_screen(
                        screen,
                        callouts_top=top_labs,
                        callouts_bottom=bot_labs,
                    )
                )
                last_sid = None
                i = skip_screen_leftovers(lines, i, screen)
            else:
                chunks.append(render_callouts(labels, "top"))
            continue
        if kind == "bullet-grid":
            grid_html, ni = consume_bullet_grid(lines, i, terms)
            if grid_html:
                chunks.append(grid_html)
                i = ni
                continue
        if fname.startswith("07-effects-") and is_voice_routing_bullet(line.strip()):
            block_html, ni = consume_voice_routing_block(lines, i, terms, fname)
            if block_html:
                chunks.append(block_html)
                i = ni
                continue
        inline_early = next(
            (
                spec
                for spec in INLINE_FIGURES
                if spec["after"].search(line.strip())
                and not spec.get("keep_trigger", True)
            ),
            None,
        )
        if inline_early:
            ni = consume_inline_figure(line, lines, i, chunks)
            if ni is not None:
                i = ni
                continue
        if kind == "num-table":
            table_html, ni = consume_numeric_table(lines, i, terms)
            if table_html:
                chunks.append(table_html)
                i = ni
                continue
        if kind == "table":
            block_html, ni = consume_pitch_shifter_delay_block(
                lines, i, terms, fname
            )
            if block_html:
                chunks.append(block_html)
                i = ni
                continue
            table_html, ni = consume_defn_table(lines, i, terms)
            if table_html:
                chunks.append(table_html)
                i = ni
                continue
        if kind == "h1":
            sid = slugify(line)
            chunks.append(f'<h1 id="{sid}">{tags(line, heading=True)}</h1>')
            i += 1
            continue
        if kind == "h2":
            sid = slugify(line)
            chunks.append(f'<h2 id="{sid}">{tags(line, heading=True)}</h2>')
            ni = consume_inline_figure(line, lines, i, chunks)
            i = ni if ni is not None else i + 1
            continue
        if kind == "h3":
            sid = slugify(line)
            chunks.append(f'<h3 id="{sid}">{tags(line, heading=True)}</h3>')
            ni = consume_inline_figure(line, lines, i, chunks)
            i = ni if ni is not None else i + 1
            continue
        if kind == "h4":
            block_html, ni = consume_vcf_distortion_vcf_routing(
                lines, i, terms, fname
            )
            if block_html:
                chunks.append(block_html)
                i = ni
                continue
            stub_i = consume_identical_params_stub_run(lines, i)
            if stub_i is not None:
                i = stub_i
                continue
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and classify(lines[j]) == "num-table":
                table_html, ni = consume_numeric_table(lines, i, terms)
                if table_html:
                    chunks.append(table_html)
                    i = ni
                    continue
            if j < len(lines) and (
                is_chart_header_row(lines[j]) or is_yesno_row(lines[j])
            ):
                table_html, ni = consume_matrix_table(lines, i, terms)
                if table_html:
                    chunks.append(table_html)
                    i = ni
                    continue
            cls = ""
            diagram_title = gated_reverb_diagram_title(line)
            heading = diagram_title or line
            if is_bullet_param_heading(line):
                heading = re.sub(r"^•\s+", "", line.strip())
            if (
                not diagram_title
                and is_param_heading(line)
                and not is_enum_heading(line)
                and not toc_heading_kind(line)
            ):
                cls = ' class="param-name"'
            sid = slugify(heading)
            chunks.append(
                f'<h4 id="{sid}"{cls}>{tags(heading, heading=True)}</h4>'
            )
            ni = consume_inline_figure(line, lines, i, chunks)
            i = ni if ni is not None else i + 1
            continue
        if kind == "algo":
            m = ALGO_RE.match(line)
            label = f"{m.group(1)} {m.group(2).strip()}" if m else line
            sid = slugify(label)
            algo_tag = "h2" if fname.startswith("07-effects-") else "h3"
            chunks.append(
                f'<{algo_tag} id="{sid}" class="algo">{tags(label, heading=True)}</{algo_tag}>'
            )
            i += 1
            continue
        if kind == "named-range-cont":
            i += 1
            continue
        if kind == "range":
            parsed = parse_range_line(line)
            name, rng = parsed
            line_buf = line
            clauses: list[str] = []
            trailing_desc: str | None = None
            clause, desc = split_range_clause_and_desc(rng)
            if clause:
                clauses.append(clause)
            trailing_desc = desc
            j = i + 1
            while j < len(lines):
                s = lines[j].strip()
                if not s:
                    k = j + 1
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k >= len(lines):
                        break
                    if is_secondary_range_line(lines[k]):
                        j = k
                        s = lines[j].strip()
                    elif parse_range_line(lines[k]):
                        break
                    elif not range_incomplete(
                        RANGE_RE.match(line_buf).group(2).strip()
                        if RANGE_RE.match(line_buf)
                        else ""
                    ):
                        break
                    else:
                        j = k
                        s = lines[j].strip()
                if is_secondary_range_line(s):
                    c, d = parse_secondary_range_line(s)
                    if c:
                        clauses.append(c)
                    if d:
                        trailing_desc = d
                    j += 1
                    continue
                joined = range_join(line_buf, s)
                if not joined:
                    break
                line_buf = joined
                clause, desc = split_range_clause_and_desc(
                    RANGE_RE.match(line_buf).group(2).strip()
                )
                clauses = [clause] if clause else clauses
                trailing_desc = desc or trailing_desc
                j += 1
            sid = slugify(name)
            chunks.append(
                f'<h4 id="{sid}" class="param-name"><span class="param">{html.escape(name)}</span>'
                f'<span class="range">{format_range_html(" ".join(clauses))}</span></h4>'
            )
            if trailing_desc:
                chunks.append(f"<p>{tags(trailing_desc)}</p>")
            i = j
            continue
        if kind == "tip":
            rest = TIP_RE.match(line).group(1)
            chunks.append(f'<aside class="tip"><p>{tags(rest)}</p></aside>')
            i += 1
            continue
        if kind == "vfd":
            mock = vfd_unit(line)
            if mock:
                chunks.append(mock)
            i += 1
            continue
        if "...." in line or "……" in line:
            items = re.split(r"\.{3,}", line)
            lis = []
            for item in items:
                tip = item.strip(" .")
                if not tip:
                    continue
                lis.append(f"<li>{tags(tip)}</li>")
            if lis:
                chunks.append("<ul class=\"tips\">" + "".join(lis) + "</ul>")
                i += 1
                continue
        if EFFECTS_ALGO_INTRO_RE.search(line):
            chunks.append(f"<p>{tags(line)}</p>")
            table_html, ni = consume_effects_algorithm_table(lines, i + 1, terms)
            if table_html:
                chunks.append(table_html)
                i = ni
                continue
        if is_delay_tempo_chart_intro(line):
            i = skip_delay_tempo_chart_section(lines, i)
            continue
        tagged = tags(line)
        inline_spec = next(
            (spec for spec in INLINE_FIGURES if spec["after"].search(line)), None
        )
        if inline_spec and not inline_spec.get("keep_trigger", True):
            ni = consume_inline_figure(line, lines, i, chunks)
            i = ni if ni is not None else i + 1
            continue
        if not used_button:
            press_at = line.lower().find("press")
            if 0 <= press_at <= 80:
                for b in BUTTONS:
                    if re.search(rf"\b{re.escape(b)}\b", line):
                        chunks.append(button_float(b))
                        used_button = True
                        break
        if line.lower().startswith("note:") or line.lower().startswith("important:"):
            chunks.append(f'<aside class="note"><p>{tagged}</p></aside>')
        else:
            chunks.append(f"<p>{tagged}</p>")
        ni = consume_inline_figure(line, lines, i, chunks)
        if ni is not None:
            i = ni
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        nxt = lines[j].strip() if j < len(lines) else ""
        trig = match_vfd_trigger(line, catalog, trigger_used, nxt)
        if trig:
            screen = catalog.get("screens", {}).get(trig)
            nxt_kind = classify(lines[j]) if j < len(lines) else "blank"
            has_json_callouts = bool(
                screen and (screen.get("callouts_top") or screen.get("callouts_bottom"))
            )
            if screen and (nxt_kind != "callouts" or has_json_callouts):
                chunks.append(render_vfd_screen(screen))
                last_sid = None
                i = skip_screen_leftovers(lines, i + 1, screen)
                continue
            last_sid = trig
        i += 1
    figs = []
    for img, cap in FIGURES.get(fname, []):
        if (IMAGES / img).exists():
            figs.append(
                f'<figure class="figure"><img src="images/{html.escape(img)}" alt="{html.escape(cap)}">'
                f"<figcaption>{apply_tags(cap, load_terms())}</figcaption></figure>"
            )
    model = ""
    if fname == "01-controls.html":
        model = (
            '<aside class="model-note"><p>The TS-12 uses the same OS and display. '
            "Differences: 76-key weighted action, channel (not polyphonic) aftertouch, "
            "release-velocity MIDI, stock <span class=\"term\">SW-6</span> damper instead of "
            "<span class=\"term\">SW-2</span>.</p></aside>"
        )
    return model + "".join(figs) + "\n".join(chunks)


def chrome(
    filename: str,
    body: str,
    *,
    extra_scripts: list[str] | None = None,
) -> str:
    title = TITLES[filename]
    idx = NAV_ORDER.index(filename) if filename in NAV_ORDER else -1
    prev_l = next_l = ""
    if idx > 0:
        prev_name = NAV_ORDER[idx - 1]
        prev_title = TITLES[prev_name]
        prev_href = prev_name
        if prev_title.startswith("Section "):
            prev_href = f"{prev_name}#{section_anchor(prev_title)}"
        prev_l = f'<a href="{prev_href}">← {prev_title}</a>'
    if 0 <= idx < len(NAV_ORDER) - 1:
        next_name = NAV_ORDER[idx + 1]
        next_title = TITLES[next_name]
        next_href = next_name
        if next_title.startswith("Section "):
            next_href = f"{next_name}#{section_anchor(next_title)}"
        next_l = f'<a href="{next_href}">{next_title} →</a>'
    h1_id = ""
    if title.startswith("Section "):
        h1_id = f' id="{section_anchor(title)}"'
    scripts = ""
    if extra_scripts:
        scripts = "\n" + "\n".join(
            f'  <script src="{html.escape(s)}"></script>' for s in extra_scripts
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} — ENSONIQ TS-10/TS-12 Musician’s Manual</title>
  <link rel="stylesheet" href="css/manual.css">
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="chrome">
      <a href="index.html"><span class="brand">ENSONIQ</span>
      <span class="product">TS-10 / TS-12 Musician’s Manual</span></a>
    </div>
  </header>
  <nav class="section-nav">
    <div>{prev_l}</div>
    <div><a href="index.html">Contents</a> · <a href="search.html">Search</a></div>
    <div>{next_l}</div>
  </nav>
  <article class="manual" id="main">
    <header class="title-block">
      <p class="brand-line">Performance / Composition Synthesizer · Version 3.0</p>
      <h1{h1_id}>{html.escape(title)}</h1>
    </header>
    {body}
  </article>
  <footer class="site-footer">
    Copyright © 1993, 1995 ENSONIQ Corp. All rights reserved.
    This is a working HTML transcription for the Toniq project; original pagination
    and the printed Index are omitted.
  </footer>{scripts}
</body>
</html>
"""


def build_index() -> str:
    items = []
    for name in NAV_ORDER:
        if name == "index.html":
            continue
        title = TITLES[name]
        href = name
        if title.startswith("Section "):
            href = f"{name}#{section_anchor(title)}"
        items.append(f'<li><a href="{href}">{html.escape(title)}</a></li>')
    body = (
        "<p>Start here. The printed Index is not transcribed. "
        "Use <a href=\"search.html\">Search</a> to find parameters, buttons, and terms across pages.</p>"
        '<nav class="toc-page"><ol>' + "\n".join(items) + "</ol></nav>"
        '<aside class="edition-note"><p>Source: <span class="term">TS-10 Musician’s Manual</span> v3.0. '
        "TS-12 differences are called out in model notes. Button photographs belong in "
        "<code>references/buttons/</code>; until they exist, keycaps are drawn in CSS.</p></aside>"
    )
    return chrome("index.html", body)


def collect_range(pages: list[str], start: int, end: int) -> list[str]:
    collected: list[str] = []
    for i in range(start - 1, min(end - 1, len(pages))):
        collected.extend(clean_page(pages[i], first=(i == start - 1)))
        collected.append("")
    return unwrap(collected)


def split_at(lines: list[str], pattern: str) -> tuple[list[str], list[str]]:
    rx = re.compile(pattern)
    for i, ln in enumerate(lines):
        if rx.match(ln.strip()):
            return lines[:i], lines[i:]
    raise SystemExit(f"split heading not found: {pattern}")


def split_parts(lines: list[str], parts: list[tuple[str, str | None]]) -> dict[str, list[str]]:
    remaining = lines
    out: dict[str, list[str]] = {}
    for i, (_fname, pat) in enumerate(parts):
        if pat is None:
            continue
        head, remaining = split_at(remaining, pat)
        out[parts[i - 1][0]] = head
    out[parts[-1][0]] = remaining
    return out


def write_delay_tempo_chart_page(terms: dict[str, list[str]]) -> None:
    body = build_delay_tempo_chart_page_body(terms)
    html_out = chrome(
        DELAY_TEMPO_CHART_FNAME,
        body,
        extra_scripts=["js/delay-tempo-calculator.js"],
    )
    (OUT / DELAY_TEMPO_CHART_FNAME).write_text(html_out, encoding="utf-8")
    print("wrote", DELAY_TEMPO_CHART_FNAME)


def write_page(
    fname: str,
    lines: list[str],
    terms: dict[str, list[str]],
    catalog: dict,
) -> None:
    SLUG_COUNTS.clear()
    USED_IDS.clear()
    # Page shell IDs are not generated through slugify but must stay unique.
    USED_IDS.add("main")
    body = to_html_body(lines, terms, fname, catalog)
    (OUT / fname).write_text(chrome(fname, body), encoding="utf-8")
    print("wrote", fname, "lines", len(lines))


def main() -> None:
    pages = load_pages()
    load_toc(pages)
    build_effect_manual_catalog(pages)
    terms = load_terms()
    catalog = load_vfd_screens()
    OUT.mkdir(exist_ok=True)
    (OUT / "index.html").write_text(build_index(), encoding="utf-8")
    for fname, (start, end) in PAGES.items():
        write_page(fname, collect_range(pages, start, end), terms, catalog)
    for start, end, parts in SPLIT_RANGES:
        chunks = split_parts(collect_range(pages, start, end), parts)
        for fname, _pat in parts:
            write_page(fname, chunks[fname], terms, catalog)
    write_delay_tempo_chart_page(terms)
    print("done")


if __name__ == "__main__":
    main()
