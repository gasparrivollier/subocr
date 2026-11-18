import csv
from fractions import Fraction as F
from pathlib import Path

import pytest

from subocr.ocr import OcrResult
from subocr.pipeline import run_pipeline
from fakes import FakeEngine
from synth import SynthSpec, SynthSub, write_video

TEXTS = ["Hola, ¿qué tal?", "Nada de nada, amigo.", "Vámonos ya mismo.", "Hasta la vista, baby."]


def engine(n=8, conf=0.95):
    return FakeEngine([OcrResult(TEXTS[i % len(TEXTS)], conf) for i in range(n)])


def rows(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def boundaries_video(tmp_path_factory):
    p = tmp_path_factory.mktemp("pl") / "b.mp4"
    spec = SynthSpec(n_frames=330, subs=[
        SynthSub(30, 89, ("Hola, ¿qué tal?",)),
        SynthSub(120, 179, ("Nada de nada, amigo.",)),
        SynthSub(180, 239, ("Vámonos ya mismo.", "Sin mirar atrás.")),   # back-to-back with the previous
        SynthSub(300, 329, ("Hasta la vista, baby.",)),                 # runs to the last frame
    ])
    return p, write_video(p, spec)


def test_boundaries_exact_frames(boundaries_video, synth_config, tmp_path):
    p, pts = boundaries_video
    r = run_pipeline(p, synth_config, tmp_path, engine())
    got = [(s.start_frame, s.end_frame, s.end_next_frame) for s in r.spans]
    assert got == [(30, 89, 90), (120, 179, 180), (180, 239, 240), (300, 329, None)]
    assert r.spans[0].start_pts == pts[30] and r.spans[0].end_next_pts == pts[90]
    assert r.n_frames == 330 and len(r.events) == 4
    assert [e.text for e in r.events] == TEXTS


def test_outputs_written(boundaries_video, synth_config, tmp_path):
    p, _ = boundaries_video
    run_pipeline(p, synth_config, tmp_path / "out", engine())
    assert len(rows(tmp_path / "out" / "events.csv")) == 4
    assert (tmp_path / "out" / "subs.srt").read_text(encoding="utf-8").count("-->") == 4
    assert len((tmp_path / "out" / "frame_index.csv").read_text().splitlines()) == 331


def test_frame_zero_event(synth_config, tmp_path):
    p = tmp_path / "z.mp4"
    write_video(p, SynthSpec(n_frames=40, subs=[SynthSub(0, 9, ("Primera línea aquí.",))]))
    r = run_pipeline(p, synth_config, tmp_path / "o", engine())
    assert [(s.start_frame, s.end_frame, s.end_next_frame) for s in r.spans] == [(0, 9, 10)]


def test_no_subtitles_outputs(synth_config, tmp_path):
    p = tmp_path / "n.mp4"
    write_video(p, SynthSpec(n_frames=40))
    r = run_pipeline(p, synth_config, tmp_path / "o", engine())
    assert r.events == []
    assert len((tmp_path / "o" / "events.csv").read_text(encoding="utf-8-sig").splitlines()) == 1
    assert (tmp_path / "o" / "subs.srt").read_text() == ""
    assert len((tmp_path / "o" / "frame_index.csv").read_text().splitlines()) == 41


def test_ui_clutter_makes_no_events(synth_config, tmp_path):
    p = tmp_path / "c.mp4"
    write_video(p, SynthSpec(n_frames=60, cursor=True, progress_bar=True))
    assert run_pipeline(p, synth_config, tmp_path / "o", engine()).spans == []


def test_ui_clutter_does_not_break_real_event(synth_config, tmp_path):
    p = tmp_path / "c2.mp4"
    write_video(p, SynthSpec(n_frames=90, cursor=True, progress_bar=True,
                             subs=[SynthSub(20, 59, ("Hola, ¿qué tal?",))]))
    r = run_pipeline(p, synth_config, tmp_path / "o", engine())
    assert [(s.start_frame, s.end_frame, s.end_next_frame) for s in r.spans] == [(20, 59, 60)]


def test_vfr_timestamps_from_pts(synth_config, tmp_path):
    p = tmp_path / "v.mp4"
    pts = write_video(p, SynthSpec(n_frames=90, vfr_drop_every=7, subs=[SynthSub(20, 60, ("Hola, ¿qué tal?",))]))
    r = run_pipeline(p, synth_config, tmp_path / "o", engine())
    e = r.events[0]
    assert (e.start_frame, e.end_frame) == (20, 60)
    assert e.end_next_pts - e.start_pts == pts[61] - pts[20]
    assert e.end_next_pts - e.start_pts != F(41, 30)  # not frames / fps


def test_offset_applied_in_outputs(synth_config, tmp_path):
    p = tmp_path / "off.mp4"
    write_video(p, SynthSpec(n_frames=90, subs=[SynthSub(45, 70, ("Hola, ¿qué tal?",))]))
    run_pipeline(p, synth_config, tmp_path / "o", engine(), offset=F(1))
    row = rows(tmp_path / "o" / "events.csv")[0]
    assert row["start_frame"] == "45" and row["start_ts"] == "00:00:00.500"
    assert "00:00:00,500 -->" in (tmp_path / "o" / "subs.srt").read_text(encoding="utf-8")


def test_debug_images_named_by_final_event_id(boundaries_video, synth_config, tmp_path):
    p, _ = boundaries_video
    dbg = tmp_path / "dbg"
    run_pipeline(p, synth_config, tmp_path / "o", engine(), debug_dir=dbg)
    assert sorted(x.name for x in dbg.iterdir()) == [f"event_{i:04d}.png" for i in range(1, 5)]


def test_low_confidence_flagged(synth_config, tmp_path):
    p = tmp_path / "lc.mp4"
    write_video(p, SynthSpec(n_frames=60, subs=[SynthSub(10, 40, ("Hola, ¿qué tal?",))]))
    run_pipeline(p, synth_config, tmp_path / "o", engine(conf=0.4))
    assert rows(tmp_path / "o" / "events.csv")[0]["needs_review"] == "true"


@pytest.mark.parametrize("cancel_after", [5, 20])
def test_cancel_leaves_no_outputs(boundaries_video, synth_config, tmp_path, cancel_after):
    from subocr.pipeline import Cancelled
    p, _ = boundaries_video
    out, dbg = tmp_path / "o", tmp_path / "dbg"
    calls = {"n": 0}

    def should_cancel():
        calls["n"] += 1
        return calls["n"] > cancel_after

    with pytest.raises(Cancelled):
        run_pipeline(p, synth_config, out, engine(), debug_dir=dbg, should_cancel=should_cancel)
    assert not [f for f in out.rglob("*") if f.is_file()]
    assert not list(dbg.glob("*.png"))
