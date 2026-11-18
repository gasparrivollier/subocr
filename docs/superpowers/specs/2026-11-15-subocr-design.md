# subocr: burned-in subtitle extractor for screen recordings — design

## Intent
Extract burned-in subtitles from a screen recording of a streaming player as
discrete events (start/end frame, start/end PTS timestamp, text, confidence)
to feed a subtitling analysis (durations, gaps, reading speed, line length,
possibly shot-change sync). **Accuracy of boundaries matters more than speed.**

## Accuracy definition (decided with user)
Accuracy is measured **in recording frames**: boundaries must be exact
relative to the recording. Matching the episode's original timeline is out of
scope (capture jitter, player latency); `--offset` only corrects a constant shift.
Acceptance: >=95% of event boundaries within +-1 recording frame of a manual
or reference-SRT ground truth.

## Goals
- CLI `subocr` with `probe`, `sample`, `run`, `compare` commands.
- Timestamps from frame PTS (exact rationals via `time_base`), never `frame/fps`.
- Detect events with cheap mask processing; OCR once per event on a fused image.
- Outputs: `events.csv`, `subs.srt`, optional per-event debug PNGs.
- Pluggable mask strategies (`outline`, `box`), configurable ROI, exclusion
  rectangles, language, OCR engine (paddle default, tesseract alternative).
- Post-processing: fuzzy merge, short/empty drop, UI-noise blocklist,
  `needs_review` flag for low confidence (flag, never drop).

## Non-goals
- Matching episode time automatically; reading embedded subtitle tracks;
  GUI; real-time processing; multi-language per run.
- Later phase only: PySceneDetect shot-change distances, summary stats.

## Anti-goals (failure even if it "works")
- Events triggered by player UI/cursor.
- Silently wrong boundaries (off-by-one, back-dated/forward-dated by hysteresis).
- Timestamps computed from frame count.

## Decisions
- **Dense by default**: `sample_step: 1`. Coarse sampling is opt-in; on a
  detected change the window is rescanned densely (not pure binary search),
  using a ring buffer over a sequential decode. PyAV must decode every frame
  anyway; sampling only saves mask work. Warn that K must stay below the
  shortest plausible event (~20 frames at 60 fps -> K<=6).
- **Boundary definition**: `start_frame` = first frame where subtitle is fully
  present; `end_frame` = last frame present; export also `end_next_frame`
  (first frame after, where gone) so durations are unambiguous. Hysteresis
  confirms a transition but boundaries are back-dated to the first frame of
  the transition. Fades: boundary at first frame >= 50% of final text pixel
  count (rule configurable).
- **Timestamps**: keep PTS as `Fraction`; CSV also has `start_pts`/`end_pts`
  as exact fractions; SRT millisecond precision (rounded, not truncated).
  Duration = `end_pts - start_pts` (documented whether it includes the final
  frame's display interval; default: use `end_next_pts - start_pts`).
- **PTS anomalies**: log gaps and repeated identical frames near boundaries;
  mark affected events `boundary_uncertain=true` in CSV.
- **Fusion/OCR input**: per-pixel min (default) or median of up to ~15 evenly
  spaced grayscale ROI frames; pixels outside the dilated text mask set to
  background; inverted to black-on-white for both engines. Tesseract: psm 6,
  2-3x upscale, binarized.
- **Decode cost**: crop to ROI at decode (ffmpeg crop filter or immediate numpy
  slice) before any other work.
- **Validation**: `subocr compare events.csv reference.srt` reports boundary
  error in recording frames (histogram, % within +-1).
- **Stack (my call)**: Python via a `uv` venv pinned to 3.11/3.12 (3.14 likely
  lacks `paddlepaddle` wheels); `av`, `opencv-python`, `numpy`, `rapidfuzz`,
  `pyyaml`, `typer`; `paddleocr`+`paddlepaddle`; optional `pytesseract`,
  `scenedetect`. System: `ffmpeg` present; `tesseract`,
  `tesseract-langpack-spa` need `dnf install` if Tesseract is wanted.
- Layout and config as in the original brief (`subocr/{cli,probe,video,roi,
  masks,segment,fuse,ocr,post,export}.py`, `tests/`, `config.example.yaml`,
  `README.md`), plus `compare` in `export.py` or `validate.py`.

## MVP scope (decided with user: "quick MVP to see how it works first")
Long-term goal: usable by a non-technical person. The MVP is a developer
tool to learn how the approach behaves on real video; ease of use is deferred.

**In the MVP**
- `probe`, `sample` (needed to tune on real frames), `run`, all with
  PTS-exact timestamps and dense (every-frame) segmentation.
- `outline` mask strategy; `box` only if the real video turns out to need it.
- ROI + exclusion rectangles via YAML config; sensible defaults so
  `subocr run video.mp4` works without a config.
- Fusion, one OCR engine (my call: PaddleOCR, pip-only, no sudo; Tesseract
  later), basic post-processing (merge, drop short/empty, UI regex,
  `needs_review`).
- Outputs: `events.csv`, `subs.srt`, `--debug-dir` images.
- Unit tests for segmentation on synthetic frames and for SRT/timestamp
  formatting.

**Deferred (post-MVP)**
- Non-tech UX: guided setup (pick the subtitle area on a sample frame),
  drag-and-drop or GUI, one-click install, plain-language errors.
- Fade handling (50% rule): XOR/OR change detection would split a fading
  subtitle; revisit only if the real video fades subtitles.
- `compare` validation, `sample_step > 1` speed mode, Tesseract adapter,
  `--to-cfr`, PySceneDetect and summary stats, `boundary_uncertain` flags.

**Correction UI (decided with user: layout B, post-MVP)**
Local browser app opened by the tool after a run (`subocr review results/`).
Shows the real recording frame at the selected event, a timeline of event
blocks (flagged `needs_review` in red), an editable text box, frame-step
(back/forward) buttons, "set start here" / "set end here", and edge dragging
on the timeline. Edits are in recording frames (timestamps re-derived from
the stored PTS of that frame), saved to a corrected `events.csv` + `subs.srt`,
keeping the original untouched. Needs the run to store per-frame PTS (an
index) so any frame can be shown and timed exactly. MVP only has to write
that index so the UI can be added without re-processing. Builder decides the
stack (my guess: small local Python server + plain HTML/JS).

**Distribution (decided with user): Windows .exe, post-MVP**
Final product is a self-contained Windows .exe for non-technical users; the
MVP is developed and run on Fedora from source. Constraints this puts on the
MVP code so packaging stays cheap:
- **No external binaries.** `probe` uses PyAV (stream/time_base/avg vs r
  frame rate), not the `ffprobe` CLI; no `ffmpeg` subprocess in the core path
  (`--to-cfr` is deferred and may use PyAV or be dropped).
- **OCR engine changed (my call, replaces the earlier PaddleOCR default):**
  RapidOCR on onnxruntime (same PaddleOCR detection/recognition models, ONNX
  format). Much lighter than `paddlepaddle`, pip-only, works on Python 3.12+
  and packages cleanly with PyInstaller. Models bundled offline. Engine stays
  behind the adapter interface; `paddleocr` and Tesseract remain optional.
  Spanish accuracy is to be verified on the real video; if weak, swap the
  recognition model or add Tesseract (bundled tessdata).
- **Paths and config** via `pathlib`, no shell assumptions, no Linux-only
  calls; UI served on localhost and opened with the default browser.
- **Building the .exe needs Windows** (PyInstaller does not cross-compile):
  use a Windows machine or a GitHub Actions `windows-latest` runner. Not part
  of the MVP.
- Non-tech entry point later: double-click the .exe -> pick video -> pick
  subtitle area on a sample frame -> run -> review UI opens.

**UI scope (decided with user, 2026-11-17) — SUPERSEDES the correction UI above**
No correction/review UI: the user edits the SRT in a separate subtitle editor.
The app only needs: (1) choose/upload a video file, (2) see progress,
(3) locate the exported `.srt`, (4) see errors if any. Public GitHub repo is
acceptable for the Windows build (ask again before creating/pushing).

**Window UI (decided with user, 2026-11-17; mockups approved)**
One small PySide6 (Qt) window (~600x320; switched from `tkinter` on 2026-11-17 because the user found tkinter ugly), four states, each with a Snoopy image
(user states copyright is not a concern, so the images ship inside the app):
1. **Start** — sleeping Snoopy gif (`source.gif`, animated), "Drag a video here /
   Choose video…" (drag-and-drop onto the window works, plus the button).
2. **Working** — typing gif (`snoopy-typing.gif`, animated), file name, stage
   text ("Scanning frames…", "Reading text… 120 of 161"), progress bar with %,
   Cancel button. Heavy work runs in a background thread; window stays responsive.
3. **Done** — sunglasses still (`images.jpg`), "Done: N subtitles found", full path
   of the `.srt`, buttons "Show in folder" (Explorer with the file selected) and
   "Another video".
4. **Error** — screaming still (`44e94c…jpg`, cropped to head and tape), plain-language
   message, details saved to `subocr.log`, buttons "Show log" and "Try another".
- Images fill a 160x160 rectangle with cover-style cropping.
- Output: folder next to the video named `<video name>_subtitles/` with
  `subs.srt`, `events.csv`, `frame_index.csv`.
- No options in the window (my call: no offset field or ROI controls); defaults
  only. Language fixed to Spanish.
- My calls, not yet confirmed: estimated time left is shown only if reliable
  (else omitted); window code is separated from a testable progress/controller
  layer; PySide6-Essentials and Pillow are the UI dependencies.

**Windows packaging (decided with user, 2026-11-17)**
Audience: an individual user on their own PC (not IT-managed). Native rewrite,
MSI/WiX, MSIX and a hosted service were considered and rejected.
- **Format:** PyInstaller *folder* mode (an `.exe` plus its libraries), delivered
  as a single `.zip` the user unzips and runs. No installer for now; an Inno
  Setup installer can be added later without changing the app.
- **Build:** GitHub Actions `windows-latest` builds the zip on a release tag
  (PyInstaller cannot build Windows binaries from Fedora). Needs a GitHub repo;
  pushing it is outward-facing, so ask the user first.
- **Self-contained and offline:** OCR models bundled inside the folder, no
  downloads at run time (verify models load from the bundle with the network
  off), PyAV's bundled FFmpeg only, no external binaries.
- **Known risks, accepted:** unsigned `.exe` triggers SmartScreen and rare
  antivirus false positives (document "More info -> Run anyway"); folder is
  ~250-400 MB; Windows-specific issues (paths with accents/spaces, console
  encoding) can only be tested on a real Windows machine.
- **First version front end (my call, not yet confirmed):** drag a video onto
  the `.exe` (or double-click and type/paste a path) -> console progress ->
  `results` folder next to the video with `events.csv`, `subs.srt`,
  `frame_index.csv`, then the folder opens. A local browser UI (the planned
  correction UI) is the next step, not part of this first package.
- **Input assumption (user premise):** footage is black screen with white
  subtitles, sometimes a few seconds of real video/player UI first. The Disney+
  UI exclusion preset for the intro is a separate hardening task.

Design choices above stay valid; the MVP just builds a subset, with module
boundaries kept so the deferred pieces and a friendlier front end can be
added without rewrites.

## Status of inputs
No recording exists yet; subtitle style and language (likely Spanish) are
unknown. Therefore build order:
1. Everything not needing the video: probe, decode/PTS, ROI, both masks,
   segmentation + hysteresis, fusion, post, exports, `compare`, unit tests on
   synthetic frames (rendered text on moving background, fades, back-to-back
   subs, UI-like overlays) and SRT/timestamp formatting, plus a generated
   synthetic test video (including VFR) for end-to-end runs.
2. When the recording arrives: `sample`, tune ROI/exclusions/mask strategy
   *before* touching segmentation thresholds; validate on a 2-3 minute clip
   with no OCR, spot-check 10 events; then OCR.

## Left to the builder
Exact threshold defaults, morphology kernel sizes, config schema validation,
logging format, test fixtures, README content. Record recommendation for the
user: OBS 60 fps constant, low CRF/high bitrate.

## Builder check (self-read)
Open questions a builder would ask, and my calls:
- *Does duration include the last frame's interval?* My call: yes, use
  `end_next_pts - start_pts`; CSV also exposes both pts values.
- *Fade rule?* My call: 50% of final pixel count, configurable.
- *Where is ground-truth for acceptance?* Not available yet; `compare` works
  against a reference SRT or manual CSV when the user supplies one.
- *Python version?* My call: uv + 3.12.
