import os
import re
import sys
import time
from pathlib import Path

import pytest

from subocr.app.job import Job
from subocr.ocr import OcrResult
from fakes import FakeEngine
from synth import SynthSpec, SynthSub, write_video

TEXTS = ["Hola, ¿qué tal?", "Nada de nada, amigo.", "Vámonos ya mismo.", "Hasta la vista, baby."]


def factory(n=8, conf=0.95):
    return lambda cfg: FakeEngine([OcrResult(TEXTS[i % 4], conf) for i in range(n)])


def run_job(job: Job, timeout=120):
    job.start()
    events, t0 = [], time.time()
    while time.time() - t0 < timeout:
        events += job.poll()
        if events and events[-1].kind in ("done", "error", "cancelled"):
            return events
        time.sleep(0.02)
    raise AssertionError(f"job did not finish: {events[-3:]}")


@pytest.fixture(scope="module")
def video(tmp_path_factory):
    p = tmp_path_factory.mktemp("job") / "Mi película ñ.mp4"
    write_video(p, SynthSpec(n_frames=330, subs=[
        SynthSub(30, 89, ("Hola, ¿qué tal?",)), SynthSub(120, 179, ("Nada de nada, amigo.",)),
        SynthSub(180, 239, ("Vámonos ya mismo.", "Sin mirar atrás.")), SynthSub(300, 329, ("Hasta la vista, baby.",))]))
    return p


def test_job_done(video):
    ev = run_job(Job(video, factory()))
    last = ev[-1]
    assert last.kind == "done" and last.n_subtitles == 4
    assert last.srt_path.name == "subs.srt" and last.srt_path.parent.name.startswith("Mi película ñ_subtitles")
    assert last.srt_path.read_text(encoding="utf-8").count("-->") == 4
    pcts = [e.percent for e in ev if e.kind == "progress"]
    assert pcts == sorted(pcts) and pcts[-1] <= 100


def test_job_progress_stages(video):
    ev = run_job(Job(video, factory()))
    stages = {e.stage for e in ev if e.kind == "progress"}
    assert "Scanning frames…" in stages
    assert any(re.fullmatch(r"Reading text… \d+ of \d+ subtitles", s) for s in stages)


def test_rerun_does_not_overwrite(video):
    first = run_job(Job(video, factory()))[-1].srt_path
    first.write_text("my hand-edited subtitles", encoding="utf-8")
    second = run_job(Job(video, factory()))[-1].srt_path
    assert second != first and first.read_text(encoding="utf-8") == "my hand-edited subtitles"


def test_job_zero_subtitles_is_done_not_error(tmp_path):
    p = tmp_path / "none.mp4"
    write_video(p, SynthSpec(n_frames=40))
    last = run_job(Job(p, factory()))[-1]
    assert last.kind == "done" and last.n_subtitles == 0 and last.srt_path.exists()


def test_job_non_video_is_error(tmp_path):
    p = tmp_path / "fake.mp4"
    p.write_text("not a video")
    last = run_job(Job(p, factory()))[-1]
    assert last.kind == "error" and last.message and "Traceback" not in last.message
    assert last.log_path.exists() and "ProbeError" in last.log_path.read_text(encoding="utf-8")


def test_job_cancel(video):
    before = set(video.parent.glob("*_subtitles*"))
    job = Job(video, factory())
    job.start()
    job.cancel()
    t0, ev = time.time(), []
    while time.time() - t0 < 60 and not (ev and ev[-1].kind in ("done", "error", "cancelled")):
        ev += job.poll()
        time.sleep(0.02)
    assert ev[-1].kind == "cancelled"
    assert sum(1 for e in ev if e.kind in ("done", "error", "cancelled")) == 1
    assert set(video.parent.glob("*_subtitles*")) == before  # cancelled run leaves no folder behind


def test_job_unexpected_exception_is_error(video):
    def boom(cfg):
        raise RuntimeError("boom")
    last = run_job(Job(video, boom))[-1]
    assert last.kind == "error" and "boom" in last.log_path.read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform == "win32" or os.geteuid() == 0,
                    reason="directory permissions are not enforced for root or on Windows")
def test_job_unwritable_destination(tmp_path):
    ro = tmp_path / "ro"
    ro.mkdir()
    p = ro / "v.mp4"
    write_video(p, SynthSpec(n_frames=30))
    ro.chmod(0o555)
    try:
        last = run_job(Job(p, factory()))[-1]
    finally:
        ro.chmod(0o755)
    assert last.kind == "error" and "can't be saved" in last.message
