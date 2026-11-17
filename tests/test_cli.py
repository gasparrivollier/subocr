from fractions import Fraction as F

import pytest
from typer.testing import CliRunner

import subocr.cli as cli
from subocr.ocr import OcrResult
from fakes import FakeEngine
from synth import SynthSpec, SynthSub, write_video

runner = CliRunner()


@pytest.fixture(scope="module")
def vid(tmp_path_factory):
    p = tmp_path_factory.mktemp("cli") / "v.mp4"
    write_video(p, SynthSpec(n_frames=90, subs=[SynthSub(20, 59, ("Hola, ¿qué tal?",))]))
    return p


@pytest.fixture(scope="module")
def vfr_vid(tmp_path_factory):
    p = tmp_path_factory.mktemp("cli") / "vfr.mp4"
    write_video(p, SynthSpec(n_frames=60, vfr_drop_every=7))
    return p


def test_parse_every():
    assert cli.parse_every("30s") == 30 and cli.parse_every("1m") == 60 and cli.parse_every("90") == 90
    assert cli.parse_every("0.5s") == F(1, 2)
    with pytest.raises(ValueError):
        cli.parse_every("abc")


def test_probe_command_vfr_warning(vfr_vid):
    r = runner.invoke(cli.app, ["probe", str(vfr_vid)])
    assert r.exit_code == 0 and "WARNING" in r.output and "640" in r.output


def test_probe_command_cfr_has_no_warning(vid):
    r = runner.invoke(cli.app, ["probe", str(vid)])
    assert r.exit_code == 0 and "WARNING" not in r.output


def test_sample_writes_three_files_per_sample(vid, tmp_path):
    r = runner.invoke(cli.app, ["sample", str(vid), "--every", "1s", "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    names = sorted(p.name for p in tmp_path.iterdir())
    assert len(names) == 9 and names[0] == "sample_001_full.png"
    assert {n.split("_", 2)[2] for n in names} == {"full.png", "roi.png", "mask.png"}


def test_run_with_fake_engine(vid, tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "make_engine", lambda *a, **k: FakeEngine([OcrResult("Hola, ¿qué tal?", 0.95)]))
    r = runner.invoke(cli.app, ["run", str(vid), "--out", str(tmp_path)])
    assert r.exit_code == 0, r.output
    assert {p.name for p in tmp_path.iterdir()} >= {"events.csv", "subs.srt", "frame_index.csv"}
    assert "1 event" in r.output


def test_errors_are_one_line(tmp_path, vid):
    for args in (["run", str(tmp_path / "nope.mp4"), "--out", str(tmp_path / "o")],
                 ["run", str(vid), "--out", str(tmp_path / "o"), "--offset", "abc"],
                 ["run", str(vid), "--out", str(tmp_path / "o"), "--config", str(tmp_path / "missing.yaml")],
                 ["probe", str(tmp_path / "nope.mp4")]):
        r = runner.invoke(cli.app, args)
        assert r.exit_code == 1, args
        assert "Error:" in r.output and "Traceback" not in r.output, args
