# Packaging the Windows app

Folder-mode PyInstaller build (an `.exe` plus its libraries), zipped for delivery.

```bash
pip install -e ".[build]"                       # PyInstaller
pyinstaller packaging/subocr_app.spec --noconfirm
python packaging/make_smoke_video.py smoke.mp4  # synthetic 2-subtitle video
dist/subocr/subocr --selftest smoke.mp4 smoke_out   # Windows: dist\subocr\subocr.exe
# expect selftest.json = {"events": 2, "srt": ...}; exit code 0
```

`--selftest` runs the real pipeline headless and writes `selftest.json` next to the results
(the windowed `.exe` has no console to print to).

## Measured on Linux (dry run, 2026-11-17)

* `dist/subocr/`: **675 MB** on disk, **356 MB** as a zip.
* Largest parts: PyAV's FFmpeg libs 101 MB, Qt (PySide6) 98 MB, OpenCV's own FFmpeg libs 93 MB + cv2 79 MB,
  ONNX Runtime 73 MB, OCR models 32 MB. Two copies of FFmpeg are bundled (PyAV and OpenCV); replacing the few
  OpenCV calls with NumPy/Pillow would remove roughly 170 MB (not done; optional follow-up).
* Selftest with **no network** (`unshare -rn`): 2 events, correct text and timestamps, exit 0, OCR models loaded
  from inside the bundle (`_internal/rapidocr/models`).
* The `rapidocr` wheel ships its three ONNX models, so the build needs no download step.

Windows sizes will differ a little; the first real Windows build (GitHub Actions) gives the true numbers.

## For users

Unzip the folder anywhere and double-click `subocr.exe`. The build is unsigned, so Windows may show
"Windows protected your PC": click **More info -> Run anyway**.
