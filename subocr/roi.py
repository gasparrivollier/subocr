"""Region of interest: crop box and exclusion rectangles."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import Config


@dataclass(frozen=True, eq=False)
class Roi:
    box: tuple[int, int, int, int]   # x0, y0, x1, y1 in full-frame pixels
    ignore: np.ndarray               # bool, crop-shaped; True = excluded area

    def crop(self, image: np.ndarray) -> np.ndarray:
        x0, y0, x1, y1 = self.box
        return image[y0:y1, x0:x1]


def build_roi(cfg: Config, width: int, height: int) -> Roi:
    r = cfg.roi
    x0, x1 = round(r.left * width), round(r.right * width)
    y0, y1 = round(r.top * height), round(r.bottom * height)
    ignore = np.zeros((max(y1 - y0, 0), max(x1 - x0, 0)), dtype=bool)
    for e in cfg.exclude:
        ex0, ex1 = round(e.left * width), round(e.right * width)
        ey0, ey1 = round(e.top * height), round(e.bottom * height)
        # intersect with the ROI, shift to crop coordinates
        ix0, ix1 = max(ex0, x0) - x0, min(ex1, x1) - x0
        iy0, iy1 = max(ey0, y0) - y0, min(ey1, y1) - y0
        if ix1 > ix0 and iy1 > iy0:
            ignore[iy0:iy1, ix0:ix1] = True
    return Roi((x0, y0, x1, y1), ignore)
