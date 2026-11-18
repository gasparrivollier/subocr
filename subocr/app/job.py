"""Background job: runs the pipeline in a thread and reports progress as events (no GUI code here)."""
from __future__ import annotations

import queue
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, Optional

from ..config import Config
from ..ocr import OcrEngine, make_engine
from ..pipeline import Cancelled, run_pipeline
from .paths import friendly_message, log_path_for, unique_output_dir

EngineFactory = Callable[[Config], OcrEngine]


@dataclass(frozen=True)
class JobEvent:
    kind: Literal["progress", "done", "error", "cancelled"]
    stage: str = ""
    percent: int = 0
    n_subtitles: int = 0
    srt_path: Optional[Path] = None
    message: str = ""
    log_path: Optional[Path] = None


def _default_engine(cfg: Config) -> OcrEngine:
    return make_engine(cfg.ocr, cfg.post)


class Job:
    def __init__(self, video: Path, engine_factory: EngineFactory | None = None):
        self.video = Path(video)
        self._engine_factory = engine_factory or _default_engine
        self._events: "queue.Queue[JobEvent]" = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_percent = 0

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="subocr-job", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def poll(self) -> list[JobEvent]:
        out = []
        while True:
            try:
                out.append(self._events.get_nowait())
            except queue.Empty:
                return out

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    # ---- worker side
    def _progress(self, stage: str, done: int, total: Optional[int]) -> None:
        if stage == "scanning":
            text = "Scanning frames…"
            pct = int(50 * done / total) if total else 0
        elif stage == "reading text":
            text = f"Reading text… {done} of {total} subtitles"
            pct = 50 + int(50 * done / total) if total else 50
        else:
            return
        self._last_percent = max(self._last_percent, min(pct, 100))
        self._events.put(JobEvent("progress", stage=text, percent=self._last_percent))

    def _run(self) -> None:
        out_dir: Path | None = None
        try:
            out_dir = unique_output_dir(self.video)
            out_dir.mkdir(parents=True)  # fail early if the destination is not writable
            cfg = Config()
            engine = self._engine_factory(cfg)
            result = run_pipeline(self.video, cfg, out_dir, engine, progress=self._progress,
                                  should_cancel=self._cancel.is_set)
            self._events.put(JobEvent("done", percent=100, n_subtitles=len(result.events),
                                      srt_path=out_dir / "subs.srt"))
        except Cancelled:
            self._remove_if_empty(out_dir)
            self._events.put(JobEvent("cancelled"))
        except BaseException as exc:  # noqa: BLE001 - the window must always get a terminal event
            log = log_path_for(self.video, out_dir)
            try:
                log.write_text(f"{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}", encoding="utf-8")
            except OSError:
                pass
            self._events.put(JobEvent("error", message=friendly_message(exc), log_path=log))

    @staticmethod
    def _remove_if_empty(path: Path | None) -> None:
        if path is None:
            return
        try:
            path.rmdir()  # only succeeds when empty
        except OSError:
            pass
