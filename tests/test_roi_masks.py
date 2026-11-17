import cv2
import numpy as np

from subocr.config import Config, MaskCfg, Rect
from subocr.masks import make_mask
from subocr.roi import build_roi
from synth import SynthSpec, SynthSub, render_frame, sub_layer


def frame_with(spec: SynthSpec, i: int = 0) -> np.ndarray:
    layers = {k: sub_layer(spec.size, s.lines) for k, s in enumerate(spec.subs)}
    return cv2.cvtColor(render_frame(spec, i, layers), cv2.COLOR_RGB2BGR)


def test_build_roi_default_1080p():
    assert build_roi(Config(), 1920, 1080).box == (0, 702, 1920, 1080)


def test_exclusion_marks_ignore():
    from dataclasses import replace
    roi = build_roi(replace(Config(), exclude=(Rect(0.97, 1.0, 0.0, 1.0),)), 1920, 1080)
    assert roi.ignore.shape == (1080 - 702, 1920)
    assert roi.ignore[1048 - 702:].all()
    assert not roi.ignore[: 1048 - 702].any()


def test_crop_is_roi_slice():
    roi = build_roi(Config(), 640, 360)
    img = np.zeros((360, 640, 3), np.uint8)
    assert roi.crop(img).shape == (360 - 234, 640, 3)


def test_mask_finds_outlined_text():
    spec = SynthSpec(subs=[SynthSub(0, 9, ("Hola, ¿qué tal?",))])
    roi = build_roi(Config(), 640, 360)
    mask = make_mask(roi.crop(frame_with(spec)), roi.ignore, MaskCfg())
    _, alpha = sub_layer(spec.size, spec.subs[0].lines)
    alpha_crop = alpha[roi.box[1]:]
    assert mask.sum() > 300
    assert (mask & alpha_crop).sum() / mask.sum() >= 0.8


def test_big_bright_patch_without_text_is_ignored():
    crop = np.full((120, 400, 3), 20, np.uint8)
    crop[30:80, 100:220] = 250  # big white block (e.g. a play button)
    mask = make_mask(crop, np.zeros(crop.shape[:2], bool), MaskCfg())
    assert mask.sum() < 50


def test_cursor_below_min_pixels():
    spec = SynthSpec(n_frames=10, cursor=True)
    roi = build_roi(Config(), 640, 360)
    mask = make_mask(roi.crop(frame_with(spec, 3)), roi.ignore, MaskCfg())
    assert mask.sum() < Config().segmentation.min_pixels


def test_ignore_zeroes_mask():
    spec = SynthSpec(subs=[SynthSub(0, 9, ("Hola, ¿qué tal?",))])
    roi = build_roi(Config(), 640, 360)
    crop = roi.crop(frame_with(spec))
    assert make_mask(crop, np.ones(crop.shape[:2], bool), MaskCfg()).sum() == 0
