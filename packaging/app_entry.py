"""PyInstaller entry point (absolute imports only; a frozen entry script cannot use relative ones)."""
import multiprocessing
import os
import sys

multiprocessing.freeze_support()
# A windowed Windows .exe has no console: stdout/stderr are None, which breaks print() and logging.
for _name in ("stdout", "stderr"):
    if getattr(sys, _name) is None:
        setattr(sys, _name, open(os.devnull, "w"))

from subocr.app.main import main  # noqa: E402

raise SystemExit(main())
