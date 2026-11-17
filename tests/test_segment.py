from fractions import Fraction as F

import numpy as np
import pytest

from subocr.config import SegCfg
from subocr.models import FrameStat
from subocr.segment import frame_change, segment

STEP = F(1, 30)
CFG = SegCfg(min_pixels=300, change_thresh=0.3, hysteresis_frames=2)


def stats(pixels, changes=None, pts=None):
    changes = changes or {}
    return [FrameStat(i, pts[i] if pts else i * STEP, p, changes.get(i, 0.0)) for i, p in enumerate(pixels)]


def mask(*cells, shape=(10, 10)):
    m = np.zeros(shape, bool)
    for r, c in cells:
        m[r, c] = True
    return m


def test_frame_change():
    a = np.zeros((10, 10), bool); a.flat[:100] = True
    assert frame_change(a, a) == 0.0
    assert frame_change(mask((0, 0)), mask((5, 5))) == 1.0
    assert frame_change(mask(), mask()) == 0.0
    half = np.zeros((10, 10), bool); half.flat[50:] = True
    assert frame_change(a, half) == pytest.approx(0.5)
    b = np.zeros((20, 10), bool); b.flat[:100] = True
    c = np.zeros((20, 10), bool); c.flat[50:150] = True  # shares 50, 50 new each side
    assert frame_change(b, c) == pytest.approx(100 / 150)
    assert frame_change(None, a) == 0.0


def test_single_event():
    spans = segment(stats([0] * 5 + [500] * 10 + [0] * 5), CFG)
    assert len(spans) == 1
    s = spans[0]
    assert (s.start_frame, s.end_frame, s.end_next_frame) == (5, 14, 15)
    assert s.start_pts == 5 * STEP and s.end_pts == 14 * STEP and s.end_next_pts == 15 * STEP


def test_one_frame_dropout_inside_event_not_split():
    spans = segment(stats([500] * 5 + [0] + [500] * 5), CFG)
    assert [(s.start_frame, s.end_frame) for s in spans] == [(0, 10)]


def test_one_frame_blip_ignored():
    assert segment(stats([0] * 5 + [500] + [0] * 5), CFG) == []


def test_back_to_back_replacement():
    spans = segment(stats([500] * 20, {10: 0.8}), CFG)
    assert [(s.start_frame, s.end_frame, s.end_next_frame) for s in spans] == [(0, 9, 10), (10, 19, None)]


def test_one_frame_glitch_not_split():
    spans = segment(stats([500] * 20, {10: 0.8, 11: 0.8}), CFG)
    assert len(spans) == 1


def test_event_at_frame_zero_and_last_frame():
    spans = segment(stats([500] * 10), CFG)
    assert len(spans) == 1
    s = spans[0]
    assert (s.start_frame, s.end_frame, s.end_next_frame) == (0, 9, None)
    assert s.end_next_pts == 9 * STEP + STEP


def test_vfr_pts_carried():
    pts = [F(i, 30) + (F(1, 60) if i > 6 else 0) for i in range(20)]
    spans = segment(stats([0] * 5 + [500] * 8 + [0] * 7, pts=pts), CFG)
    s = spans[0]
    assert s.start_pts == pts[5] and s.end_pts == pts[12] and s.end_next_pts == pts[13]


def test_n_equals_one():
    spans = segment(stats([0] * 5 + [500] + [0] * 5), SegCfg(min_pixels=300, hysteresis_frames=1))
    assert [(s.start_frame, s.end_frame, s.end_next_frame) for s in spans] == [(5, 5, 6)]


def test_empty_input():
    assert segment([], CFG) == []
