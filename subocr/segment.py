"""Event segmentation from per-frame stats. Dense (every frame), pure, hysteresis-confirmed,
boundaries back-dated to the first frame of each transition."""
from __future__ import annotations

from typing import Sequence

import numpy as np

from .config import SegCfg
from .models import FrameStat, Span


def frame_change(prev: np.ndarray | None, cur: np.ndarray) -> float:
    """XOR / OR of two boolean masks; 0.0 if there is no previous mask or both are empty."""
    if prev is None:
        return 0.0
    union = np.count_nonzero(prev | cur)
    if union == 0:
        return 0.0
    return float(np.count_nonzero(prev ^ cur) / union)


def segment(stats: Sequence[FrameStat], cfg: SegCfg) -> list[Span]:
    n_stats = len(stats)
    if n_stats == 0:
        return []
    n = max(cfg.hysteresis_frames, 1)
    thr = cfg.change_thresh
    present = [s.text_pixels > cfg.min_pixels for s in stats]
    change = [s.change for s in stats]

    def window_is(i: int, value: bool) -> bool:
        # windows cut short by the end of the video count as confirmed
        return all(present[j] == value for j in range(i, min(i + n, n_stats)))

    def stable(i: int) -> bool:
        return all(change[j] <= thr for j in range(i + 1, min(i + n, n_stats)))

    spans: list[Span] = []

    def close(start: int, end: int, nxt: int | None) -> None:
        if nxt is not None:
            end_next_pts = stats[nxt].pts
        elif n_stats >= 2:
            end_next_pts = stats[end].pts + (stats[end].pts - stats[end - 1].pts if end > 0 else 0)
        else:
            end_next_pts = stats[end].pts
        spans.append(Span(
            start_frame=stats[start].index, end_frame=stats[end].index,
            end_next_frame=None if nxt is None else stats[nxt].index,
            start_pts=stats[start].pts, end_pts=stats[end].pts, end_next_pts=end_next_pts,
        ))

    cur: int | None = None
    for i in range(n_stats):
        if cur is None:
            if present[i] and window_is(i, True):
                cur = i
        elif not present[i] and window_is(i, False):
            close(cur, i - 1, i)
            cur = None
        elif (i > cur and present[i - 1] and present[i] and change[i] > thr
              and change[i - 1] <= thr and stable(i)):
            close(cur, i - 1, i)
            cur = i
    if cur is not None:
        close(cur, n_stats - 1, None)
    return spans
