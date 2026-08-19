#!/usr/bin/env python3
"""Build a file://-safe MiniSearch index from manual HTML pages."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANUAL = ROOT / "manual"
SKIP = {"search.html"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title = ""
        self.heading = ""
        self.chunks: list[tuple[str, str, str]] = []  # id, heading, text
        self._buf: list[str] = []
        self._id = ""
        self._in = False
        self._tag = ""
        self._capture_title = False
        self._current_h = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = dict(attrs)
        if tag == "title":
            self._capture_title = True
            self._buf = []
        if tag in {"h1", "h2", "h3", "h4"}:
            self._flush()
            self._id = ad.get("id") or ""
            self._in = True
            self._tag = tag
            self._buf = []
        elif tag in {"p", "li", "dt", "dd", "figcaption"} and not self._in:
            self._in = True
            self._tag = tag
            self._buf = []
            self._id = ad.get("id") or self._id

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._capture_title:
            self.title = "".join(self._buf).split("—")[0].strip()
            self._capture_title = False
            self._buf = []
        if tag in {"h1", "h2", "h3", "h4"} and self._in:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self._current_h = text
            if not self.heading:
                self.heading = text
            self.chunks.append((self._id, text, text))
            self._in = False
            self._buf = []
        elif tag in {"p", "li", "dt", "dd", "figcaption"} and self._in:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if text:
                self.chunks.append((self._id, self._current_h, text))
            self._in = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._capture_title or self._in:
            self._buf.append(data)

    def _flush(self) -> None:
        return


def main() -> None:
    docs = []
    n = 0
    for path in sorted(MANUAL.glob("*.html")):
        if path.name in SKIP:
            continue
        parser = PageParser()
        parser.feed(path.read_text(encoding="utf-8", errors="replace"))
        for hid, heading, text in parser.chunks:
            if len(text) < 8:
                continue
            n += 1
            docs.append(
                {
                    "id": n,
                    "url": path.name + (f"#{hid}" if hid else ""),
                    "title": parser.title or path.stem,
                    "heading": heading,
                    "text": text[:800],
                }
            )
    out = MANUAL / "js/search-index.js"
    out.parent.mkdir(exist_ok=True)
    payload = json.dumps(docs, ensure_ascii=False)
    out.write_text(
        "window.TONIQ_SEARCH_DOCS = " + payload + ";\n",
        encoding="utf-8",
    )
    print("indexed", len(docs), "chunks ->", out)


if __name__ == "__main__":
    main()
