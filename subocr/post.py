"""Post-processing: drop noise, merge fragments, flag low confidence."""
from __future__ import annotations

import re
from dataclasses import replace
from typing import Sequence

from rapidfuzz import fuzz

from .config import PostCfg
from .models import Event
from .ocr import is_ui_text

_WORD = re.compile(r"[^\W\d_]{2,}")  # a real word: >= 2 letters (unicode-aware)


def _is_noise(text: str, post: PostCfg) -> bool:
    if not text.strip():
        return True
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if all(is_ui_text(ln, post) for ln in lines):
        return True
    return not _WORD.search(text)  # spinner/button junk such as "C 11 6"


def _merge(a: Event, b: Event) -> Event:
    best = a if a.confidence >= b.confidence else b
    return replace(a, end_frame=b.end_frame, end_next_frame=b.end_next_frame, end_pts=b.end_pts,
                   end_next_pts=b.end_next_pts, text=best.text, confidence=best.confidence)


def clean_events(events: Sequence[Event], post: PostCfg, min_confidence: float) -> list[Event]:
    kept = [e for e in sorted(events, key=lambda e: e.start_frame) if not _is_noise(e.text, post)]
    merged: list[Event] = []
    for e in kept:
        if merged:
            prev = merged[-1]
            gap = e.start_frame - prev.end_frame - 1
            if gap <= post.merge_max_gap_frames and fuzz.ratio(prev.text, e.text) / 100 >= post.merge_similarity:
                merged[-1] = _merge(prev, e)
                continue
        merged.append(e)
    long_enough = [e for e in merged if e.end_frame - e.start_frame + 1 >= post.min_event_frames]
    return [replace(e, id=i, needs_review=e.confidence < min_confidence) for i, e in enumerate(long_enough, 1)]
