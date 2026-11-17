import cv2
import numpy as np

from subocr.config import Config, MaskCfg
from subocr.fuse import fuse, pick_sample_indices
from subocr.masks import make_mask
from subocr.roi import build_roi
from synth import SynthSpec, SynthSub, render_frame, sub_layer


def test_pick_all_when_short():
    assert pick_sample_indices(10, 19) == list(range(10, 20))


def test_pick_evenly():
    idx = pick_sample_indices(0, 99, 15)
    assert len(idx) == 15 and idx[0] == 0 and idx[-1] == 99
    assert all(b > a for a, b in zip(idx, idx[1:]))


def test_pick_single_frame():
    assert pick_sample_indices(7, 7) == [7]


def _crops_and_masks(n=8):
    spec = SynthSpec(subs=[SynthSub(0, n, ("Hola, ¿qué tal?",))], n_frames=n + 1)
    layers = {0: sub_layer(spec.size, spec.subs[0].lines)}
    roi = build_roi(Config(), 640, 360)
    crops = [roi.crop(cv2.cvtColor(render_frame(spec, i, layers), cv2.COLOR_RGB2BGR)) for i in range(n)]
    masks = [make_mask(c, roi.ignore, MaskCfg()) for c in crops]
    return crops, masks, layers[0][1][roi.box[1]:]


def test_fuse_output_contract():
    crops, masks, _ = _crops_and_masks()
    out = fuse(crops, masks)
    assert out.dtype == np.uint8 and out.ndim == 2
    assert out.shape == (crops[0].shape[0] + 20, crops[0].shape[1] + 20)
    assert (out[:10] == 255).all() and (out[:, :10] == 255).all()


def test_fuse_removes_moving_background():
    crops, masks, alpha = _crops_and_masks()
    out = fuse(crops, masks)[10:-10, 10:-10]
    near_text = cv2.dilate(alpha.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
    assert (out[alpha & (out < 128)]).size > 100                      # dark text where the text is
    assert (out[~near_text] < 250).mean() < 0.01                        # nothing else survives
