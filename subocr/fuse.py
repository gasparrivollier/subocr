"""Temporal fusion: combine several frames of one subtitle into one clean OCR image."""
from __future__ import annotations

from typing import Sequence

import cv2
import numpy as np

BORDER = 10


def pick_sample_indices(start: int, end: int, max_frames: int = 15) -> list[int]:
    """Evenly spaced frame indices in [start, end] (inclusive), ends included."""
    count = end - start + 1
    if count <= max_frames:
        return list(range(start, end + 1))
    return [start + round(k * (count - 1) / (max_frames - 1)) for k in range(max_frames)]


def fuse(crops: Sequence[np.ndarray], masks: Sequence[np.ndarray]) -> np.ndarray:
    """Black text on white. Per-pixel minimum of the grayscale crops keeps bright static text and
    drops moving bright background; only pixels near text present in >=50% of masks are kept."""
    gray = np.stack([cv2.cvtColor(c, cv2.COLOR_BGR2GRAY) for c in crops]).min(axis=0)
    stable = (np.mean(np.stack(masks), axis=0) >= 0.5).astype(np.uint8)
    stable = cv2.dilate(stable, np.ones((7, 7), np.uint8)).astype(bool)
    out = 255 - np.where(stable, gray, 0).astype(np.uint8)
    return cv2.copyMakeBorder(out, BORDER, BORDER, BORDER, BORDER, cv2.BORDER_CONSTANT, value=255)
