from fractions import Fraction

import pytest

from subocr.probe import ProbeError, probe
from subocr.video import iter_frames
from synth import SynthSpec, SynthSub, write_video


@pytest.fixture(scope="module")
def cfr(tmp_path_factory):
    p = tmp_path_factory.mktemp("v") / "cfr.mp4"
    spec = SynthSpec(subs=[SynthSub(10, 29, ("Hola, ¿qué tal?",))], n_frames=45)
    return p, write_video(p, spec), spec


@pytest.fixture(scope="module")
def vfr(tmp_path_factory):
    p = tmp_path_factory.mktemp("v") / "vfr.mp4"
    spec = SynthSpec(n_frames=45, vfr_drop_every=7)
    return p, write_video(p, spec), spec


def test_probe_cfr(cfr):
    p, _, spec = cfr
    info = probe(p)
    assert (info.width, info.height) == (640, 360)
    assert info.avg_frame_rate == Fraction(30)
    assert info.is_vfr is False
    assert info.n_frames in (None, spec.n_frames)


def test_probe_vfr(vfr):
    assert probe(vfr[0]).is_vfr is True


def test_probe_errors(tmp_path):
    with pytest.raises(ProbeError):
        probe(tmp_path / "missing.mp4")
    txt = tmp_path / "not_video.mp4"
    txt.write_text("hello")
    with pytest.raises(ProbeError):
        probe(txt)


def test_iter_frames_pts_exact(cfr):
    p, pts, spec = cfr
    frames = list(iter_frames(p))
    assert [f.index for f in frames] == list(range(spec.n_frames))
    assert [f.pts for f in frames] == pts
    assert frames[0].image.shape == (360, 640, 3) and frames[0].image.dtype.name == "uint8"


def test_iter_frames_vfr_preserves_gaps(vfr):
    p, pts, _ = vfr
    got = [f.pts for f in iter_frames(p)]
    assert got == pts
    assert len({b - a for a, b in zip(got, got[1:])}) > 1
