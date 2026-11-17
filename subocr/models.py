"""Small shared data types."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction


@dataclass(frozen=True)
class FrameStat:
    """Per-frame measurements from pass 1."""
    index: int
    pts: Fraction
    text_pixels: int
    change: float  # XOR/OR of this frame's mask vs the previous frame's


@dataclass(frozen=True)
class Span:
    """A run of frames showing one subtitle (before OCR)."""
    start_frame: int
    end_frame: int                 # last frame with the subtitle
    end_next_frame: int | None     # first frame without it; None if the video ended
    start_pts: Fraction
    end_pts: Fraction
    end_next_pts: Fraction         # falls back to end_pts + last frame interval


@dataclass(frozen=True)
class Event:
    id: int
    start_frame: int
    end_frame: int
    end_next_frame: int | None
    start_pts: Fraction
    end_pts: Fraction
    end_next_pts: Fraction
    text: str
    confidence: float
    needs_review: bool = False

    @classmethod
    def from_span(cls, id: int, span: Span, text: str, confidence: float) -> "Event":
        return cls(id, span.start_frame, span.end_frame, span.end_next_frame,
                   span.start_pts, span.end_pts, span.end_next_pts, text, confidence)
