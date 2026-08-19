# Figure extraction

From repo root:

```
# VFD strips and bitmaps already extracted to manual/images/
pdfimages -png "docs/Ensoniq TS-10 Musicians Manual.pdf" /tmp/ts-imgs/img

# Full pages used as diagrams (rear/front panel, effects, MIDI chart)
pdftoppm -png -r 110 -f 31 -l 36 "docs/Ensoniq TS-10 Musicians Manual.pdf" manual/images/page
pdftoppm -png -r 110 -f 88 -l 95 "docs/Ensoniq TS-10 Musicians Manual.pdf" manual/images/page
pdftoppm -png -r 110 -f 166 -l 172 "docs/Ensoniq TS-10 Musicians Manual.pdf" manual/images/page
pdftoppm -png -r 110 -f 408 -l 409 "docs/Ensoniq TS-10 Musicians Manual.pdf" manual/images/page

# Section 1 inline diagrams (200 dpi crops into manual/images/):
#   p.31  rear-panel.png, foot-switches.png
#   p.33  front-panel-controls.png
#   p.36  performance-controllers.png
#   p.39  bankset-display.png
#   p.47  kbd-naming.png
#   p.65  preset-save-bankset-buttons.png
pdftoppm -png -r 200 -f 31 -l 42 "docs/Ensoniq TS-10 Musicians Manual.pdf" /tmp/toniq-s1/p
pdftoppm -png -r 200 -f 46 -l 48 "docs/Ensoniq TS-10 Musicians Manual.pdf" /tmp/toniq-s2/p

# Preface line-art (vector drawings; pdfimages misses these). Crop from 200 dpi pages:
#   p.8  Power inlet, polarized plugs
#   p.9  Ground loops FIG. 1 / FIG. 2
#   p.10 Amplification hookup
#   p.12 Floppy write-protect / density windows
pdftoppm -png -r 200 -f 8 -l 12 "docs/Ensoniq TS-10 Musicians Manual.pdf" /tmp/ts-preface/p
```

Musician’s Manual already has a text layer (`pdftotext -layout`). SysEx spec is a scan: `ocrmypdf --force-ocr --sidecar notes/transcript/sysex-ocr.txt`.
