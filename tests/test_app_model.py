from pathlib import Path

from subocr.app.job import JobEvent
from subocr.app.model import AppModel, State


class FakeJob:
    """Scripted job: each poll() returns the next batch of events."""
    instances = []

    def __init__(self, video, batches=()):
        self.video, self.batches = video, list(batches)
        self.started = self.cancelled = False
        self.joined = 0
        FakeJob.instances.append(self)

    def start(self): self.started = True
    def cancel(self): self.cancelled = True
    def poll(self): return self.batches.pop(0) if self.batches else []
    def join(self, timeout=None): self.joined += 1


def model(*batches):
    FakeJob.instances.clear()
    return AppModel(lambda video: FakeJob(video, batches))


V = Path("/videos/ep1.mp4")
DONE = JobEvent("done", percent=100, n_subtitles=161, srt_path=Path("/videos/ep1_subtitles/subs.srt"))


def test_start_to_working_to_done():
    m = model([JobEvent("progress", stage="Scanning frames…", percent=10)],
              [JobEvent("progress", stage="Reading text… 3 of 9 subtitles", percent=60)], [DONE])
    assert m.view.state is State.START
    m.choose(V)
    assert m.view.state is State.WORKING and m.view.video == V and FakeJob.instances[0].started
    v = m.tick()
    assert (v.state, v.stage, v.percent) == (State.WORKING, "Scanning frames…", 10)
    assert m.tick().percent == 60
    v = m.tick()
    assert v.state is State.DONE and v.n_subtitles == 161 and v.srt_path.name == "subs.srt" and v.message == ""


def test_zero_subtitles_message():
    m = model([JobEvent("done", percent=100, n_subtitles=0, srt_path=Path("/x/subs.srt"))])
    m.choose(V)
    v = m.tick()
    assert v.state is State.DONE and v.message == "No subtitles were found in this video."


def test_error_state_keeps_log_path():
    m = model([JobEvent("error", message="This file can't be opened as a video.", log_path=Path("/x/subocr.log"))])
    m.choose(V)
    v = m.tick()
    assert v.state is State.ERROR and v.log_path == Path("/x/subocr.log") and "can't be opened" in v.message


def test_cancel_returns_to_start():
    m = model([], [JobEvent("cancelled")])
    m.choose(V)
    m.cancel()
    assert FakeJob.instances[0].cancelled and m.view.state is State.WORKING  # waits for the job to confirm
    m.tick()
    assert m.tick().state is State.START


def test_choose_ignored_while_working():
    m = model([])
    m.choose(V)
    m.choose(Path("/other.mp4"))
    assert len(FakeJob.instances) == 1 and m.view.video == V


def test_reset_from_done_and_error():
    m = model([DONE])
    m.choose(V); m.tick()
    m.reset()
    assert m.view.state is State.START
    m = model([JobEvent("error", message="x", log_path=Path("/l"))])
    m.choose(V); m.tick()
    m.reset()
    assert m.view.state is State.START
    m.choose(V)  # can start again after an error
    assert m.view.state is State.WORKING


def test_shutdown_cancels_running_job_and_is_idempotent():
    m = model([])
    m.choose(V)
    m.shutdown(); m.shutdown()
    assert FakeJob.instances[0].cancelled
    model([]).shutdown()  # no job at all: fine
