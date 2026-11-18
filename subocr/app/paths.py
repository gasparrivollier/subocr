"""Output folder naming, log file location, plain-language errors, 'show in folder'."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable

from ..config import ConfigError
from ..probe import ProbeError
from ..video import VideoError


def unique_output_dir(video: Path) -> Path:
    """<video folder>/<name>_subtitles, or ' (2)', ' (3)'... Never reuses an existing folder."""
    video = Path(video)
    base = video.parent / f"{video.stem}_subtitles"
    candidate, n = base, 1
    while candidate.exists():
        n += 1
        candidate = video.parent / f"{video.stem}_subtitles ({n})"
    return candidate


def log_path_for(video: Path, out_dir: Path | None) -> Path:
    """subocr.log inside the output folder if it can be created, else in the temp folder."""
    if out_dir is not None:
        try:
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            return Path(out_dir) / "subocr.log"
        except OSError:
            pass
    return Path(tempfile.gettempdir()) / "subocr.log"


def friendly_message(exc: BaseException) -> str:
    if isinstance(exc, VideoError) and "timestamp" in str(exc):
        return ("This recording has no usable timestamps, so subtitle timing can't be trusted. "
                "Try recording it again with a constant frame rate.")
    if isinstance(exc, (ProbeError, VideoError, FileNotFoundError)):
        return "This file can't be opened as a video. Try a different file."
    if isinstance(exc, ConfigError):
        return "The settings file is not valid. Details were saved to the log file."
    if isinstance(exc, MemoryError):
        return "Not enough memory to process this video."
    if isinstance(exc, OSError):
        return "The results can't be saved in that folder. Move the video to a folder you can write to."
    return "Something unexpected went wrong. Details were saved to the log file."


def reveal_in_folder(path: Path, platform: str | None = None,
                     runner: Callable[..., Any] = subprocess.Popen) -> None:
    path = Path(path)
    plat = platform or sys.platform
    if plat == "win32":
        runner(["explorer", f"/select,{path}"])  # Explorer exits non-zero even on success; ignore
    elif plat == "darwin":
        runner(["open", "-R", str(path)])
    else:
        runner(["xdg-open", str(path.parent)])
