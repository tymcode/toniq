---
name: ts-html-manual
description: >-
  Conventions for the TS-10/TS-12 HTML musician’s manual (VFD tables, button
  floats, semantic CSS classes, file splits, search index). Use when adding or
  editing files under manual/, CSS, templates, or scripts/build_manual.py.
---

# HTML manual

Follow [notes/html-conventions.md](../../../notes/html-conventions.md).

## Rebuild

```
python3 scripts/build_manual.py
python3 scripts/build-search-index.py
```

Generated `manual/*.html` (except `search.html`) come from the transcript. Change the builder, not a one-off page, unless you are marking `span.ocr-suspect`.

## Must

- **Own line in the PDF = own line in HTML.** Page titles (`Wave Page`), TOC section titles (`The Sounds`, `When to Reinitialize`), parameter names (`Wave Name`), and display-label rows stay separate blocks — never joined into the following sentence. A wrapped bullet stays one `<p>`. A wrapped `Tip:` stays one `aside.tip`. Two-column setting/description lists (`00 PATCH` / prose) render as `table.defn-table`, not a concatenated paragraph. Side-by-side bullet blocks render as `table.bullet-cols`. Printed lookup charts (`LFO FREQUENCIES`, `ENVELOPE TIMES`, Delay Times/Tempo BPM) and YES/NO matrices (`GLIDE MODES`, sequencer MIDI-status) render as `table.data-table`. A wrapped `Range:` (including a parenthesis split across lines) stays inside one `span.range`.
- Split long sections only at a heading (`Wave Page`, algorithm `22` / `Dual Effects`, `Locate Page`), never at a PDF page number mid-sentence.
- Represent the 2×40 display as `figure.vfd-unit`: page label in its own left-justified cell (no button), then 3 parameter cells with 3 soft buttons above and 3 below. Empty cells keep their column. Buttons line up with the parameters they select, not with the page label. Selected field `.selected`; pressed soft button `.pressed`. Green-on-black only inside `.vfd-screen`.
- **LCD mockups are uppercase only** (device charset: `A–Z 0–9 . , : - + * _ / ( ) =`). Mixed-case text is a callout, never screen content.
- VFD font only on complete display strings: `.vfd-screen` cells and `span.lcd` (`DELAY=0000`, `*YES*`). Parameter names in body text and headings use ordinary type.
- Tag `dfn.term`, `span.param`, `span.value`, `span.lcd`, `kbd.button`, `span.function`, `aside.tip` / `aside.model-note`. Panel names from `notes/terms.json` become `kbd.button` next to press/hold/click/double-click or the word *button*. On VFD mockups, `.selected` is a solid underline (primary/cursor); `.flash-underline` is a broken underline (layered track) painted with a repeating gradient, flashing on screen.
- When prose names a hard button, use `aside.button-float` + `table.button-id` so text can wrap.
- Skip the printed Index. Keep the Ensoniq copyright footer.
- After HTML changes, regenerate `manual/js/search-index.js`.
- Printed line-art is cropped into `manual/images/` and listed in `INLINE_FIGURES`; vector drawings are invisible to the text transcript.
