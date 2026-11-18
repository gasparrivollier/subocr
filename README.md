# subocr

Extract **burned-in subtitles** from a **screen recording** (e.g. OBS capture of a streaming player) as
events with exact start/end **frame numbers**, **timestamps** from each frame's PTS, **text** and **confidence**.

Frames are measured in *recording frames*; timestamps come from the frame PTS (never `frame / fps`), so
variable-frame-rate recordings stay exact.

## Install (Fedora / Linux)

```bash
uv venv --python 3.12 .venv        # Python 3.12 (3.14 may lack wheels for some dependencies)
uv pip install --python .venv/bin/python -e ".[dev]"
```

No system `ffmpeg` is required (PyAV bundles it). OCR models (RapidOCR/ONNX) are included in the
`rapidocr` package.

## Use

```bash
.venv/bin/subocr probe video.mp4                         # resolution, frame rates, VFR warning
.venv/bin/subocr sample video.mp4 --every 30s --out samples/   # full frame + ROI crop + mask, to tune by eye
.venv/bin/subocr run video.mp4 --out results/ [--config config.yaml] [--offset 12.345] [--debug-dir dbg/]
```

Tuning workflow: `probe` -> `sample` -> look at `sample_NNN_full.png` (green box = ROI, red = excluded areas)
and `sample_NNN_mask.png` (white = what counts as text) -> adjust `config.yaml` (see `config.example.yaml`) -> `run`.
Typical fixes: widen/narrow the ROI, add an exclusion rectangle over the player progress bar or time labels.

`--offset` is in seconds: `episode_time = recording_time - offset`. Frame numbers are never shifted.

## Windows app

A small window (Snoopy included): choose or drag a video, watch the progress, find the `.srt`.
User guide: [`packaging/USER_GUIDE.md`](packaging/USER_GUIDE.md). Build and packaging notes:
[`packaging/README.md`](packaging/README.md). Run it from source with `.venv/bin/python -m subocr.app`.
The Windows zip is built by the GitHub Actions workflow `.github/workflows/build-windows.yml`
(manual run or a `v*` tag).

## Outputs

* `events.csv` — `id, start_frame, end_frame, end_next_frame, start_ts, end_ts, duration_s, text, n_lines, n_chars, cps, confidence, needs_review, start_pts, end_pts, end_next_pts` (UTF-8 with BOM, opens in Excel).
* `subs.srt` — for Subtitle Edit / Aegisub.
* `frame_index.csv` — PTS of every frame (`index, pts, pts_s`), so any frame can be timed exactly later.
* `--debug-dir` — `event_0001.png`: the fused image the OCR actually saw.

### Boundary definitions

* `start_frame`: first frame where the subtitle is present. `end_frame`: last frame where it is present.
* `end_next_frame`: first frame without it (blank if the video ends first).
* `end_ts` = PTS of `end_next_frame`; `duration_s = end_next_pts - start_pts`.
* `needs_review` = OCR confidence below `ocr.min_confidence` (events are flagged, never dropped for this).

## How it works

Pass 1 decodes every frame, crops the ROI, builds a text mask (bright, thin, unsaturated strokes next to
dark pixels) and finds subtitle runs (hysteresis against flicker; a new subtitle is detected when the mask
changes by more than `change_thresh`). Pass 2 re-decodes up to 15 frames per run, fuses them (per-pixel
minimum keeps static text, removes moving background) and OCRs once per event. Player UI text (`0:00`,
`39:41`, blocklist) is dropped per OCR box before lines are formed.

## Current limits (MVP)

Not yet: `box` mask (dark translucent box styles), fade-in/out subtitles, speed mode (`sample_step`),
Tesseract, `--to-cfr`, comparison against a reference SRT, shot-change stats, correction UI, Windows `.exe`.
See `docs/superpowers/specs/2026-11-15-subocr-design.md`.

Recommended recording settings (OBS): constant 60 fps, high bitrate / low CRF. Compression flicker is the
main enemy of the text mask.

## Tests

```bash
.venv/bin/pytest            # fast suite, synthetic lossless video, exact-frame boundary checks
.venv/bin/pytest -m slow    # also runs the real OCR model tests
```
