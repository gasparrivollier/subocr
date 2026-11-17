"""CSV / SRT / frame-index / debug-image writers. Times stay Fractions until formatted."""
from __future__ import annotations

import csv
from fractions import Fraction
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from .models import Event, FrameStat

CSV_COLUMNS = ["id", "start_frame", "end_frame", "end_next_frame", "start_ts", "end_ts", "duration_s",
               "text", "n_lines", "n_chars", "cps", "confidence", "needs_review",
               "start_pts", "end_pts", "end_next_pts"]


def _ms(t: Fraction) -> int:
    if t < 0:
        raise ValueError("negative time cannot be formatted")
    return int((t * 1000 + Fraction(1, 2)) // 1)  # round half up


def _format(t: Fraction, sep: str) -> str:
    ms = _ms(t)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def format_srt_time(t: Fraction) -> str:
    return _format(t, ",")


def format_ts(t: Fraction) -> str:
    return _format(t, ".")


def _frac(t: Fraction) -> str:
    return f"{t.numerator}/{t.denominator}"


def write_srt(path: Path, events: Sequence[Event], offset: Fraction = Fraction(0)) -> None:
    blocks = []
    for e in events:
        end = e.end_next_pts - offset
        if end < 0:
            continue  # ended before the episode starts
        start = max(e.start_pts - offset, Fraction(0))
        blocks.append(f"{len(blocks) + 1}\n{format_srt_time(start)} --> {format_srt_time(end)}\n{e.text}\n\n")
    Path(path).write_text("".join(blocks), encoding="utf-8")


def write_csv(path: Path, events: Sequence[Event], offset: Fraction = Fraction(0)) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(CSV_COLUMNS)
        for e in events:
            dur = e.end_next_pts - e.start_pts
            n_chars = len(e.text.replace("\n", ""))
            cps = n_chars / float(dur) if dur > 0 else 0.0
            shift = lambda t: format_ts(max(t - offset, Fraction(0)))  # noqa: E731
            w.writerow([
                e.id, e.start_frame, e.end_frame, "" if e.end_next_frame is None else e.end_next_frame,
                shift(e.start_pts), shift(e.end_next_pts), f"{float(dur):.3f}",
                e.text, len(e.text.split("\n")) if e.text else 0, n_chars, f"{cps:.1f}",
                f"{e.confidence:.3f}", str(e.needs_review).lower(),
                _frac(e.start_pts), _frac(e.end_pts), _frac(e.end_next_pts),
            ])


def write_frame_index(path: Path, stats: Sequence[FrameStat]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write("index,pts,pts_s\n")
        for s in stats:
            f.write(f"{s.index},{_frac(s.pts)},{float(s.pts):.6f}\n")


def write_debug_image(dir: Path, event_id: int, image: np.ndarray) -> Path:
    dir = Path(dir)
    dir.mkdir(parents=True, exist_ok=True)
    out = dir / f"event_{event_id:04d}.png"
    cv2.imwrite(str(out), image)
    return out
