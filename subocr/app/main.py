"""Entry logic for the app: open the window, or run a headless self-test (used to smoke-test the build)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..config import Config
from ..ocr import make_engine
from ..pipeline import run_pipeline
from .paths import friendly_message


def _selftest(video: Path, out_dir: Path) -> int:
    try:
        cfg = Config()
        result = run_pipeline(video, cfg, out_dir, make_engine(cfg.ocr, cfg.post))
    except BaseException as exc:  # noqa: BLE001 - report anything as JSON, never a traceback
        print(json.dumps({"error": f"{friendly_message(exc)} ({type(exc).__name__}: {exc})"}))
        return 1
    print(json.dumps({"events": len(result.events), "srt": str(out_dir / "subs.srt")}))
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
