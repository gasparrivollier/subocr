"""Entry logic for the app: open the window, or run a headless self-test (used to smoke-test the build)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..config import Config
from ..ocr import make_engine
from ..pipeline import run_pipeline
from .paths import friendly_message


def _emit(result: dict, out_dir: Path) -> None:
    """Print the result and also save it: a windowed .exe on Windows has no console to print to."""
    text = json.dumps(result)
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "selftest.json").write_text(text, encoding="utf-8")
    except OSError:
        pass
    try:
        print(text)
    except (OSError, ValueError, AttributeError):
        pass


def _selftest(video: Path, out_dir: Path) -> int:
    try:
        cfg = Config()
        result = run_pipeline(video, cfg, out_dir, make_engine(cfg.ocr, cfg.post))
    except BaseException as exc:  # noqa: BLE001 - report anything as JSON, never a traceback
        _emit({"error": f"{friendly_message(exc)} ({type(exc).__name__}: {exc})"}, out_dir)
        return 1
    _emit({"events": len(result.events), "srt": str(out_dir / "subs.srt")}, out_dir)
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--selftest":
        if len(argv) != 3:
            print(json.dumps({"error": "usage: --selftest VIDEO OUTDIR"}))
            return 1
        return _selftest(Path(argv[1]), Path(argv[2]))
    from .window import run  # imported late so --selftest works without a display
    run()
    return 0
