import json
import tkinter
from pathlib import Path

import pytest

from subocr.app.model import State, ViewState
from subocr.ocr import OcrResult
from fakes import FakeEngine
from synth import SynthSpec, SynthSub, write_video

V = Path("/videos/ep1.mp4")


class FakeModel:
    def __init__(self, view=None):
        self.view = view or ViewState()
        self.calls = []

    def tick(self): return self.view
    def choose(self, video): self.calls.append(("choose", video)); self.view = ViewState(State.WORKING, video=video, stage="Starting…")
    def cancel(self): self.calls.append(("cancel",))
    def reset(self): self.calls.append(("reset",)); self.view = ViewState()
    def shutdown(self): self.calls.append(("shutdown",))


def make_app(view=None, pick=None, reveal=None):
    from subocr.app.window import App
    try:
        return App(model=FakeModel(view), pick_file=pick or (lambda: None), reveal=reveal or (lambda p: None))
    except tkinter.TclError:
        pytest.skip("no display available for tkinter")


def text(w): return str(w.cget("text"))


def test_start_screen():
    app = make_app()
    try:
        app.update()
        assert text(app.primary_button) == "Choose video…"
        assert app.image_label.cget("image") != ""
    finally:
        app.destroy()


def test_choose_button_picks_file_and_starts():
    app = make_app(pick=lambda: V)
    try:
        app.primary_button.invoke()
        assert app.model.calls == [("choose", V)]
    finally:
        app.destroy()


def test_working_screen_shows_stage_and_percent():
    app = make_app(ViewState(State.WORKING, video=V, stage="Reading text… 3 of 9 subtitles", percent=60))
    try:
        app.update()
        assert text(app.title_label) == "ep1.mp4"
        assert text(app.status_label) == "Reading text… 3 of 9 subtitles"
        assert float(app.progress["value"]) == 60
        assert text(app.primary_button) == "Cancel"
        app.primary_button.invoke()
        assert ("cancel",) in app.model.calls
    finally:
        app.destroy()


def test_done_screen_shows_path_and_buttons():
    srt = Path("/videos/ep1_subtitles/subs.srt")
    shown = []
    app = make_app(ViewState(State.DONE, video=V, percent=100, srt_path=srt, n_subtitles=161), reveal=shown.append)
    try:
        app.update()
        assert text(app.title_label) == "Done: 161 subtitles found"
        assert text(app.path_label) == str(srt)
        assert text(app.primary_button) == "Show in folder" and text(app.secondary_button) == "Another video"
        app.primary_button.invoke()
        assert shown == [srt]
        app.secondary_button.invoke()
        assert ("reset",) in app.model.calls
    finally:
        app.destroy()


def test_done_zero_subtitles_text():
    app = make_app(ViewState(State.DONE, video=V, srt_path=Path("/x/subs.srt"), n_subtitles=0,
                             message="No subtitles were found in this video."))
    try:
        app.update()
        assert text(app.title_label) == "No subtitles were found in this video."
    finally:
        app.destroy()


def test_error_screen_shows_log_path_and_show_log_reveals_it():
    log, shown = Path("/videos/subocr.log"), []
    app = make_app(ViewState(State.ERROR, video=V, message="This file can't be opened as a video.", log_path=log),
                   reveal=shown.append)
    try:
        app.update()
        assert text(app.title_label) == "Something went wrong"
        assert text(app.status_label) == "This file can't be opened as a video."
        assert text(app.path_label) == str(log)
        assert text(app.primary_button) == "Show log" and text(app.secondary_button) == "Try another"
        app.primary_button.invoke()
        assert shown == [log]
    finally:
        app.destroy()


def test_close_calls_shutdown():
    app = make_app()
    app._on_close()
    assert ("shutdown",) in app.model.calls


# ---- headless self-test mode (used by the packaging smoke test), no display needed
def test_selftest_json(tmp_path, monkeypatch, capsys):
    import subocr.app.main as entry
    video = tmp_path / "s.mp4"
    write_video(video, SynthSpec(n_frames=120, subs=[SynthSub(20, 50, ("Hola, ¿qué tal?",)),
                                                      SynthSub(70, 100, ("Nada de nada, amigo.",))]))
    monkeypatch.setattr(entry, "make_engine", lambda *a, **k: FakeEngine(
        [OcrResult("Hola, ¿qué tal?", 0.9), OcrResult("Nada de nada, amigo.", 0.9)]))
    assert entry.main(["--selftest", str(video), str(tmp_path / "out")]) == 0
    data = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert data["events"] == 2 and Path(data["srt"]).exists()


def test_selftest_missing_file_exit_1(tmp_path, capsys):
    import subocr.app.main as entry
    assert entry.main(["--selftest", str(tmp_path / "nope.mp4"), str(tmp_path / "o")]) == 1
    assert "error" in json.loads(capsys.readouterr().out.strip().splitlines()[-1])
