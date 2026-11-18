"""Window state machine. No tkinter here, so it is testable without a display."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from .job import Job, JobEvent


class State(Enum):
    START = "start"
    WORKING = "working"
    DONE = "done"
    ERROR = "error"


@dataclass(frozen=True)
class ViewState:
    state: State = State.START
    video: Optional[Path] = None
    stage: str = ""
    percent: int = 0
    message: str = ""
    srt_path: Optional[Path] = None
    log_path: Optional[Path] = None
    n_subtitles: int = 0


class AppModel:
    def __init__(self, job_factory: Callable[[Path], Job] = Job):
        self._factory = job_factory
        self._job = None
        self.view = ViewState()

    def choose(self, video: Path) -> None:
        if self.view.state is State.WORKING:
            return
        self._job = self._factory(Path(video))
        self._job.start()
        self.view = ViewState(State.WORKING, video=Path(video), stage="Starting…")

    def tick(self) -> ViewState:
        if self._job is not None:
            for ev in self._job.poll():
                self._apply(ev)
        return self.view

    def _apply(self, ev: JobEvent) -> None:
        if self.view.state is not State.WORKING:
            return
        if ev.kind == "progress":
            self.view = replace(self.view, stage=ev.stage, percent=ev.percent)
        elif ev.kind == "done":
            msg = "No subtitles were found in this video." if ev.n_subtitles == 0 else ""
            self.view = ViewState(State.DONE, video=self.view.video, percent=100, message=msg,
                                  srt_path=ev.srt_path, n_subtitles=ev.n_subtitles)
            self._job = None
        elif ev.kind == "error":
            self.view = ViewState(State.ERROR, video=self.view.video, message=ev.message, log_path=ev.log_path)
            self._job = None
        elif ev.kind == "cancelled":
            self.view = ViewState()
            self._job = None

    def cancel(self) -> None:
        if self._job is not None and self.view.state is State.WORKING:
            self._job.cancel()

    def reset(self) -> None:
        if self.view.state in (State.DONE, State.ERROR):
            self.view = ViewState()

    def shutdown(self) -> None:
        job, self._job = self._job, None
        if job is not None:
            job.cancel()
            join = getattr(job, "join", None)
            if join:
                join(5)
