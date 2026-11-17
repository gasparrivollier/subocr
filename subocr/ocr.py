"""OCR engine adapters. Line assembly is a pure function so it can be tested without models."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from .config import ConfigError, OcrCfg, PostCfg


@dataclass(frozen=True)
class OcrResult:
    text: str          # lines joined by "\n", top to bottom
    confidence: float  # character-weighted mean of line scores; 0.0 if nothing found


class OcrEngine(Protocol):
    def read(self, image: np.ndarray) -> OcrResult: ...


@dataclass(frozen=True)
class Detection:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    score: float


def is_ui_text(text: str, post: PostCfg) -> bool:
    t = text.strip()
    if re.match(post.ui_regex, t):
        return True
    low = t.lower()
    return any(b.lower() in low for b in post.blocklist)


def _same_row(a_y0: float, a_y1: float, b: Detection) -> bool:
    overlap = min(a_y1, b.y1) - max(a_y0, b.y0)
    return overlap > 0.5 * min(a_y1 - a_y0, b.y1 - b.y0)


def assemble_lines(dets: Sequence[Detection], post: PostCfg) -> OcrResult:
    """Drop UI boxes, group boxes into rows, order them, collapse boundary duplicates."""
    kept = [d for d in dets if d.text.strip() and not is_ui_text(d.text, post)]
    rows: list[list[Detection]] = []
    row_y: list[tuple[float, float]] = []
    for d in sorted(kept, key=lambda d: (d.y0 + d.y1) / 2):
        if rows and _same_row(*row_y[-1], d):
            rows[-1].append(d)
            row_y[-1] = (min(row_y[-1][0], d.y0), max(row_y[-1][1], d.y1))
        else:
            rows.append([d])
            row_y.append((d.y0, d.y1))
    lines, weighted, chars = [], 0.0, 0
    for row in rows:
        words: list[str] = []
        prev: Detection | None = None
        for d in sorted(row, key=lambda d: d.x0):
            parts = d.text.split()
            if prev is not None and d.x0 < prev.x1 and words and parts and words[-1].lower() == parts[0].lower():
                parts = parts[1:]  # same word read twice by two overlapping boxes
            words.extend(parts)
            prev = d
            weighted += d.score * len(d.text)
            chars += len(d.text)
        lines.append(" ".join(words))
    if not chars:
        return OcrResult("", 0.0)
    return OcrResult("\n".join(lines), weighted / chars)


class RapidOcrEngine:
    def __init__(self, lang: str, post: PostCfg):
        from rapidocr import RapidOCR  # imported lazily: heavy and optional for tests
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        self.lang = lang  # default models read Latin text; per-language models come later
        self.post = post
        self._ocr = RapidOCR()

    def read(self, image: np.ndarray) -> OcrResult:
        dark = np.argwhere(image < 200)
        if dark.size == 0:
            return OcrResult("", 0.0)
        (y0, x0), (y1, x1) = dark.min(axis=0), dark.max(axis=0)
        m = 15
        crop = image[max(y0 - m, 0): y1 + m, max(x0 - 2 * m, 0): x1 + 2 * m]
        out = self._ocr(crop)
        if out.boxes is None or not len(out.txts):
            return OcrResult("", 0.0)
        dets = [Detection(float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 0].max()), float(b[:, 1].max()),
                          t, float(s)) for b, t, s in zip(out.boxes, out.txts, out.scores)]
        return assemble_lines(dets, self.post)


def make_engine(cfg: OcrCfg, post: PostCfg) -> OcrEngine:
    if cfg.engine == "rapidocr":
        return RapidOcrEngine(cfg.lang, post)
    raise ConfigError(f"unknown OCR engine '{cfg.engine}' (available: rapidocr)")
