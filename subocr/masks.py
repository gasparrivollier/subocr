"""Text mask strategies. Each returns a bool array shaped like the crop."""
from __future__ import annotations

from typing import Callable

import cv2
import numpy as np

from .config import ConfigError, MaskCfg


def _square(n: int) -> np.ndarray:
    return np.ones((max(n, 1), max(n, 1)), np.uint8)


def outline_mask(crop_bgr: np.ndarray, ignore: np.ndarray, cfg: MaskCfg) -> np.ndarray:
    """Bright, unsaturated, thin strokes (optionally next to dark pixels)."""
    hsv = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2HSV)
    v, s = hsv[..., 2], hsv[..., 1]
    m = ((v >= cfg.v_min) & (s <= cfg.s_max)).astype(np.uint8)
    if cfg.max_stroke_px > 0:  # drop big bright shapes: keep only what an opening cannot keep
        big = cv2.morphologyEx(m, cv2.MORPH_OPEN, _square(cfg.max_stroke_px + 1))
        m = m & (1 - big)
    if cfg.require_outline:
        dark = (v <= cfg.dark_v_max).astype(np.uint8)
        near_dark = cv2.dilate(dark, _square(2 * cfg.outline_radius_px + 1))
        m = m & near_dark
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, _square(cfg.open_px + 1))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, _square(cfg.close_px))
    out = m.astype(bool)
    out[ignore] = False
    return out


MASK_STRATEGIES: dict[str, Callable[[np.ndarray, np.ndarray, MaskCfg], np.ndarray]] = {
    "outline": outline_mask,
}


def make_mask(crop_bgr: np.ndarray, ignore: np.ndarray, cfg: MaskCfg) -> np.ndarray:
    try:
        fn = MASK_STRATEGIES[cfg.strategy]
    except KeyError:
        raise ConfigError(f"unknown mask strategy '{cfg.strategy}'") from None
    return fn(crop_bgr, ignore, cfg)
