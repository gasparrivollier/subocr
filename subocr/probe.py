"""Inspect a video with PyAV (no ffprobe binary needed)."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import av


class ProbeError(Exception):
    """The file could not be opened or has no video."""


@dataclass(frozen=True)
class ProbeInfo:
    width: int
    height: int
    codec: str
    r_frame_rate: Fraction
    avg_frame_rate: Fraction
    time_base: Fraction
    duration_s: float | None
    n_frames: int | None
    is_vfr: bool


def _frac(x) -> Fraction:
    return Fraction(x) if x else Fraction(0)


def probe(path: Path) -> ProbeInfo:
    path = Path(path)
    try:
        container = av.open(str(path))
    except FileNotFoundError as e:
        raise ProbeError(f"file not found: {path}") from e
    except (av.error.FFmpegError, OSError) as e:
        raise ProbeError(f"cannot open {path.name} as a video: {e}") from e
    with container:
        if not container.streams.video:
            raise ProbeError(f"{path.name} has no video stream")
        s = container.streams.video[0]
        r, avg = _frac(s.base_rate), _frac(s.average_rate)
        is_vfr = bool(r and avg and abs(float(r - avg)) / float(r) > 0.01)
        if s.duration is not None and s.time_base:
            duration = float(s.duration * s.time_base)
        elif container.duration:
            duration = container.duration / av.time_base
        else:
            duration = None
        return ProbeInfo(
            width=s.codec_context.width, height=s.codec_context.height, codec=s.codec_context.name,
            r_frame_rate=r, avg_frame_rate=avg, time_base=Fraction(s.time_base),
            duration_s=duration, n_frames=s.frames or None, is_vfr=is_vfr,
        )
