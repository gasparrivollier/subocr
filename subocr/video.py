"""Frame iteration with exact PTS."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Iterator

import av
import numpy as np


class VideoError(Exception):
    """Decoding problem (unreadable file, missing timestamps)."""


@dataclass(frozen=True)
class FrameRec:
    index: int          # decode order, from 0
    pts: Fraction       # seconds, exact
    image: np.ndarray   # BGR uint8, full frame


def iter_frames(path: Path) -> Iterator[FrameRec]:
    try:
        container = av.open(str(path))
    except (av.error.FFmpegError, OSError) as e:
        raise VideoError(f"cannot open {Path(path).name}: {e}") from e
    with container:
        if not container.streams.video:
            raise VideoError(f"{Path(path).name} has no video stream")
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for i, frame in enumerate(container.decode(stream)):
            if frame.pts is None:
                raise VideoError(f"frame {i} has no timestamp (PTS); cannot time subtitles reliably")
            yield FrameRec(i, Fraction(frame.pts) * Fraction(frame.time_base),
                           frame.to_ndarray(format="bgr24"))
