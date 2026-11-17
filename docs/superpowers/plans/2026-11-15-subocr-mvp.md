# subocr MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A CLI (`subocr probe|sample|run`) that extracts burned-in subtitles from a screen recording as frame- and PTS-exact events (CSV + SRT + debug images + per-frame PTS index).

**Architecture:** Two-pass dense pipeline. Pass 1 decodes every frame, crops the ROI, builds a text mask and records per-frame stats; a pure `segment()` turns stats into spans (hysteresis, back-dated boundaries). Pass 2 re-decodes, collects up to 15 frames per span, fuses them, OCRs once per span. Post-processing and export are pure functions over `Event` lists. OCR sits behind an adapter so engines can be swapped.

**Tech Stack:** Python 3.12 (uv venv), `av`, `opencv-python-headless`, `numpy`, `rapidocr` + `onnxruntime`, `rapidfuzz`, `pyyaml`, `typer`; dev: `pytest`, `pillow`.

**Spec:** `docs/superpowers/specs/2026-11-15-subocr-design.md` (read it first; it holds the decisions this plan relies on).

## Global Constraints

- Timestamps come from frame PTS as `fractions.Fraction`; never `frame / fps`. Convert to strings only at export.
- Dense by default: every frame is masked. No `sample_step`, binary search, `--to-cfr`, `box` mask, Tesseract, `compare`, fade handling, shot-change stats in the MVP (all deferred; unknown/deferred config keys raise `ConfigError` naming the key).
- No external binaries: probe and decode use PyAV only (no `ffprobe`/`ffmpeg` subprocess), so the project can later be packaged as a Windows `.exe`. Use `pathlib` everywhere.
- Boundaries (recording frames): `start_frame` = first frame subtitle present; `end_frame` = last frame present; `end_next_frame` = first frame after, or `None` if the video ends first. `end_next_pts` = PTS of `end_next_frame`, or `end_pts + last frame interval` if `None`. Duration = `end_next_pts - start_pts`. CSV/SRT `end_ts` = `end_next_pts`.
- Hysteresis N = `segmentation.hysteresis_frames`; confirmed transitions are back-dated to the first frame of the transition.
- Offset semantics: `episode_time = recording_time - offset` (offset in seconds, parsed as `Fraction(str)`); applied at export only.
- SRT: UTF-8, milliseconds rounded half-up. CSV: UTF-8 with BOM (`utf-8-sig`, opens correctly in Excel), `csv` module quoting.
- Defaults from the spec: roi bottom 22% (`top 0.78`), `v_min 200`, `s_max 60`, `min_pixels 300`, `change_thresh 0.3`, `hysteresis_frames 2`, `merge_similarity 0.9`, merge gap <= 2 frames, `min_event_frames 3`, `min_confidence 0.6`, blocklist `["Skip intro", "Saltar intro"]`, UI regex `^\d{1,2}:\d{2}(:\d{2})?$`, fusion cap 15 frames, `lang: es`.
- User-facing failures (bad file, bad config) print one line `Error: ...` and exit 1, never a traceback.
- `change` stat (my call, documented): `XOR / OR` of consecutive masks, 0.0 when OR is empty.

## Review Focus

1. Video with no subtitles at all: `run` succeeds, writes header-only `events.csv`, empty `subs.srt`, full `frame_index.csv` (Task 9).
2. Subtitle already visible at frame 0, or still visible at the last frame: event is kept, `end_next_frame=None`, end time falls back to last interval (Tasks 5, 9).
3. Back-to-back subtitles with zero gap, plus UI clutter (a cursor-sized blob moving through the ROI, progress bar): two events, no false events (Tasks 4, 5, 9).
4. Text with commas, quotes, newlines, accents and `¿¡`: survives CSV round-trip and SRT (Task 2).
5. Unreadable file, file with no video stream, frames without PTS, invalid ROI/config values: one-line error, exit 1 (Tasks 1, 3, 10).

---

### Task 1: Scaffold, environment, config

**Files:**
- Create: `pyproject.toml`, `subocr/__init__.py`, `subocr/config.py`, `config.example.yaml`, `tests/test_config.py`, `.gitignore` (append `.venv/`, `__pycache__/`, `results/`)
- Existing: `.gitignore` already has `.superpowers/`

**Interfaces:**
- Produces (`subocr/config.py`):
  - `class ConfigError(Exception)`
  - `@dataclass(frozen=True) Rect(top: float, bottom: float, left: float, right: float)`
  - `MaskCfg(strategy: str="outline", v_min: int=200, s_max: int=60, require_outline: bool=True, dark_v_max: int=60, outline_radius_px: int=3, open_px: int=1, close_px: int=3)`
  - `SegCfg(min_pixels: int=300, change_thresh: float=0.3, hysteresis_frames: int=2)`
  - `OcrCfg(engine: str="rapidocr", lang: str="es", min_confidence: float=0.6)`
  - `PostCfg(merge_similarity: float=0.9, merge_max_gap_frames: int=2, min_event_frames: int=3, blocklist: tuple[str,...]=("Skip intro","Saltar intro"), ui_regex: str=r"^\d{1,2}:\d{2}(:\d{2})?$")`
  - `Config(roi: Rect, exclude: tuple[Rect,...], mask: MaskCfg, segmentation: SegCfg, ocr: OcrCfg, post: PostCfg, fusion_max_frames: int=15)`
  - `load_config(path: Path | None) -> Config` (None = defaults; partial YAML overrides defaults)

- [ ] **Step 1: Create the environment.** `uv --version` (if missing: `pip install --user uv`), then `uv venv --python 3.12 .venv`, write `pyproject.toml` (package `subocr`, console script `subocr = subocr.cli:app`, deps above, dev extras `pytest`, `pillow`), `uv pip install -e ".[dev]"`. Verify: `.venv/bin/python -c "import av, cv2, rapidocr, onnxruntime"` exits 0. `git init`.
- [ ] **Step 2: Write failing tests** in `tests/test_config.py`:
  - `test_defaults_match_spec`: `load_config(None)` has `roi == Rect(0.78, 1.0, 0.0, 1.0)`, `segmentation.min_pixels == 300`, `change_thresh == 0.3`, `hysteresis_frames == 2`, `mask.v_min == 200`, `mask.s_max == 60`, `post.merge_similarity == 0.9`, `post.min_event_frames == 3`, `ocr.min_confidence == 0.6`.
  - `test_partial_yaml_overrides`: YAML with only `segmentation: {min_pixels: 100}` keeps other defaults.
  - `test_unknown_key_raises`: `segmentation: {sample_step: 4}` raises `ConfigError` whose message contains `sample_step`.
  - `test_box_strategy_rejected`: `mask: {strategy: box}` raises `ConfigError` (message says not available yet).
  - `test_bad_roi_raises`: `top >= bottom` or any value outside 0..1 raises `ConfigError`.
  - `test_missing_file_raises`: nonexistent path raises `ConfigError`.
- [ ] **Step 3: Run `.venv/bin/pytest tests/test_config.py -v`**; expect FAIL (import error).
- [ ] **Step 4: Implement `config.py`** with frozen dataclasses; one `_build(cls, data, path)` helper that rejects unknown keys. Write `config.example.yaml` mirroring the spec's example (minus `sample_step`).
- [ ] **Step 5: Run tests**; expect PASS.
- [ ] **Step 6: Commit** `git add -A && git commit -m "feat: scaffold and config loading"`

---

### Task 2: Models and export (CSV, SRT, frame index, debug images)

**Files:**
- Create: `subocr/models.py`, `subocr/export.py`, `tests/test_export.py`

**Interfaces:**
- Produces (`subocr/models.py`):
  - `@dataclass(frozen=True) FrameStat(index: int, pts: Fraction, text_pixels: int, change: float)`
  - `@dataclass(frozen=True) Span(start_frame: int, end_frame: int, end_next_frame: int | None, start_pts: Fraction, end_pts: Fraction, end_next_pts: Fraction)`
  - `@dataclass(frozen=True) Event(id: int, start_frame, end_frame, end_next_frame, start_pts, end_pts, end_next_pts, text: str, confidence: float, needs_review: bool=False)` with `@classmethod from_span(cls, id: int, span: Span, text: str, confidence: float) -> Event`
- Produces (`subocr/export.py`):
  - `format_srt_time(t: Fraction) -> str` (`HH:MM:SS,mmm`, half-up rounding, raises `ValueError` if negative)
  - `format_ts(t: Fraction) -> str` (`HH:MM:SS.mmm`, same rounding)
  - `write_srt(path: Path, events: Sequence[Event], offset: Fraction = Fraction(0)) -> None` (skips events whose shifted `end_next_pts` is negative, clamps negative start to 0)
  - `write_csv(path: Path, events: Sequence[Event], offset: Fraction = Fraction(0)) -> None`; columns in order: `id,start_frame,end_frame,end_next_frame,start_ts,end_ts,duration_s,text,n_lines,n_chars,cps,confidence,needs_review,start_pts,end_pts,end_next_pts` (pts as `num/den`; `n_chars` excludes newlines; `cps = n_chars / duration_s`; empty `end_next_frame` when `None`)
  - `write_frame_index(path: Path, stats: Sequence[FrameStat]) -> None` (columns `index,pts,pts_s`)
  - `write_debug_image(dir: Path, event_id: int, image: np.ndarray) -> Path` (`event_0001.png`)

- [ ] **Step 1: Write failing tests** in `tests/test_export.py`:
  - `test_format_srt_time`: `Fraction(3661)+Fraction(1,2)` -> `"01:01:01,500"`; `Fraction(1,2000)` -> `"00:00:00,001"`; `Fraction(1,3)` -> `"00:00:00,333"`; `Fraction(599996,10000)` -> `"00:01:00,000"` (carry); negative raises `ValueError`.
  - `test_srt_multiline_and_accents`: event text `"¿Qué haces?\nNada, niño."` writes block `1\n00:00:03,000 --> 00:00:05,000\n¿Qué haces?\nNada, niño.\n\n` (file decodes as UTF-8, no BOM).
  - `test_csv_roundtrip_hostile_text`: text `'a,b\n"c", ¡hola!'` reads back identical via `csv.DictReader(open(..., encoding="utf-8-sig", newline=""))`; for event frames 90..149, `end_next_frame` 150, pts 3 -> 5 s: `duration_s == "2.000"`-equivalent float 2.0, `end_ts == "00:00:05.000"`, `n_lines == "2"`, `cps` equals `n_chars/2.0`.
  - `test_csv_end_next_none_blank`.
  - `test_offset_shifts_and_skips`: offset `Fraction(3,2)` shifts SRT times by -1.5 s; an event ending before offset is absent from SRT but present in CSV with raw frames.
  - `test_empty_outputs`: zero events -> CSV has header only, SRT is an empty file.
  - `test_frame_index_and_debug_image`: 3 stats write 4 lines; debug image file `event_0007.png` exists and reads back with `cv2.imread`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_export.py -v`; expect FAIL.
- [ ] **Step 3: Implement** `models.py` and `export.py` with the signatures above (time math in `Fraction`; round with `(t*1000 + Fraction(1,2)) // 1`).
- [ ] **Step 4: Run tests**; expect PASS.
- [ ] **Step 5: Commit** `feat: models and exporters`

---

### Task 3: Synthetic video fixture, probe, decode

**Files:**
- Create: `tests/synth.py`, `tests/conftest.py`, `subocr/probe.py`, `subocr/video.py`, `tests/test_video.py`

**Interfaces:**
- Produces (`tests/synth.py`, test helper):
  - `@dataclass SynthSub(start: int, end: int, lines: tuple[str,...])` (frame indices, inclusive)
  - `@dataclass SynthSpec(subs: list[SynthSub], n_frames: int, size=(640,360), fps=30, vfr_drop_every: int=0, cursor: bool=False, progress_bar: bool=False)`
  - `write_video(path: Path, spec: SynthSpec) -> list[Fraction]` returns the PTS (seconds) of every written frame. Lossless FFV1 in `.mkv` via PyAV, explicit PTS on a `1/1000` time base; `vfr_drop_every=k` skips every k-th frame so PTS gaps are irregular. Frame content: moving noisy gradient background with some bright moving blobs (no outline); subtitles drawn with PIL `ImageDraw.text` (white fill, black `stroke_width=3`, DejaVu Sans Bold ~28 px, centred in bottom 22%, accents supported); optional moving cursor-sized white arrow with black outline (< 200 px area) crossing the ROI; optional progress bar (thin bright bar in a fixed strip, bottom 3%).
  - `conftest.py` fixture `synth_config()` returning a `Config` tuned for the synthetic size (`min_pixels` ~150, progress strip in `exclude`).
- Produces (`subocr/probe.py`):
  - `class ProbeError(Exception)`
  - `@dataclass(frozen=True) ProbeInfo(width: int, height: int, codec: str, r_frame_rate: Fraction, avg_frame_rate: Fraction, time_base: Fraction, duration_s: float | None, n_frames: int | None, is_vfr: bool)`
  - `probe(path: Path) -> ProbeInfo` (`is_vfr` = r vs avg rate differ by > 1%; if the container reports equal rates but packet PTS deltas vary by > 1.5x, also VFR; implementer picks the exact check, the tests decide)
- Produces (`subocr/video.py`):
  - `class VideoError(Exception)`
  - `@dataclass(frozen=True) FrameRec(index: int, pts: Fraction, image: np.ndarray)` (BGR uint8, full frame)
  - `iter_frames(path: Path) -> Iterator[FrameRec]` (`index` counts decoded frames from 0; `pts = Fraction(frame.pts) * frame.time_base`; `frame.pts is None` raises `VideoError`)

- [ ] **Step 1: Write failing tests** in `tests/test_video.py`:
  - `test_probe_cfr`: 640x360 30 fps spec -> `width==640`, `height==360`, `avg_frame_rate==Fraction(30)`, `is_vfr is False`, `n_frames` equals written count (or `None`).
  - `test_probe_vfr`: `vfr_drop_every=7` -> `is_vfr is True`.
  - `test_probe_errors`: nonexistent path and a text file each raise `ProbeError`.
  - `test_iter_frames_pts_exact`: yielded `pts` list equals `write_video`'s returned list (exact `Fraction` equality), indices `0..N-1`, shape `(360,640,3)`, dtype `uint8`.
  - `test_iter_frames_vfr_preserves_gaps`: with `vfr_drop_every=7`, `set(diff of pts)` has > 1 distinct value.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_video.py -v`; expect FAIL. (Write `synth.py` first in this step; it is the fixture, tested indirectly.)
- [ ] **Step 3: Implement `probe.py` and `video.py`** with PyAV (`av.open`, `container.streams.video[0]`, `stream.average_rate`, `stream.base_rate`).
- [ ] **Step 4: Run tests**; expect PASS. Add `tests/synth.py` smoke check: open a written file and eyeball one frame saved via `cv2.imwrite` to the scratchpad to confirm subtitle and clutter look right.
- [ ] **Step 5: Commit** `feat: probe, decode, synthetic video fixture`

---

### Task 4: ROI and outline mask

**Files:**
- Create: `subocr/roi.py`, `subocr/masks.py`, `tests/test_roi_masks.py`

**Interfaces:**
- Consumes: `Config`, `Rect`, `MaskCfg` (Task 1); `synth` helpers (Task 3).
- Produces (`subocr/roi.py`):
  - `@dataclass(frozen=True) Roi(box: tuple[int,int,int,int], ignore: np.ndarray)` with `crop(self, image: np.ndarray) -> np.ndarray` (view of `image[y0:y1, x0:x1]`); `box = (x0, y0, x1, y1)` in full-frame pixels; `ignore` is a bool array of crop shape, True where exclusion rectangles overlap.
  - `build_roi(cfg: Config, width: int, height: int) -> Roi` (pixel bounds via `round(fraction * size)`; exclusion rects are fractions of the full frame)
- Produces (`subocr/masks.py`):
  - `make_mask(crop_bgr: np.ndarray, ignore: np.ndarray, cfg: MaskCfg) -> np.ndarray` (bool, crop shape; dispatches on `cfg.strategy` through `MASK_STRATEGIES: dict[str, Callable]`)
  - `outline_mask(crop_bgr, ignore, cfg) -> np.ndarray`: HSV `V >= v_min` and `S <= s_max`; if `require_outline`, keep only pixels within `outline_radius_px` of a dark pixel (`V <= dark_v_max`); morphological open then close with the configured sizes; zero where `ignore`.

- [ ] **Step 1: Write failing tests** in `tests/test_roi_masks.py`:
  - `test_build_roi_default_1080p`: `build_roi(load_config(None), 1920, 1080).box == (0, 842, 1920, 1080)`.
  - `test_exclusion_marks_ignore`: exclude `Rect(0.97, 1.0, 0.0, 1.0)` -> bottom ~3% rows of `ignore` are True, rows above are False.
  - `test_mask_finds_outlined_text`: render `"Hola, ¿qué tal?"` with PIL (white, black stroke) on a noisy dark crop -> `mask.sum() > 300` and >= 80% of mask pixels lie inside the text bounding box.
  - `test_mask_ignores_bright_background_without_outline`: bright white patch with no dark border -> `mask.sum() < 50`.
  - `test_cursor_below_min_pixels`: small outlined arrow (synth cursor) -> `mask.sum() < 300` (default `min_pixels`).
  - `test_ignore_zeroes_mask`: text under an `ignore` region contributes 0 pixels.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** both modules (OpenCV `cvtColor`, `dilate` for the outline-proximity test, `morphologyEx`). Raise `ConfigError` for unknown strategy.
- [ ] **Step 4: Run tests**; expect PASS.
- [ ] **Step 5: Commit** `feat: ROI and outline mask`

---

### Task 5: Event segmentation

**Files:**
- Create: `subocr/segment.py`, `tests/test_segment.py`

**Interfaces:**
- Consumes: `FrameStat`, `Span` (Task 2), `SegCfg` (Task 1).
- Produces (`subocr/segment.py`):
  - `frame_change(prev: np.ndarray | None, cur: np.ndarray) -> float` (`XOR.sum() / OR.sum()`; 0.0 if `prev` is None or OR is empty)
  - `segment(stats: Sequence[FrameStat], cfg: SegCfg) -> list[Span]`

**Algorithm (decided; implementer writes the code).** `present(i) = text_pixels > min_pixels`. Let N = `hysteresis_frames`; lookahead windows truncated by the end of the video count as confirmed.
- Start: idle and `present(i)` for `i..i+N-1` -> span starts at `i` (back-dated).
- End: in a span and `not present` for N consecutive frames starting at `i` -> `end_frame = i-1`, `end_next_frame = i`.
- Replacement: in a span, `present(i-1)` and `present(i)`, `change(i) > change_thresh`, `change(j) <= change_thresh` for `j` in `i+1..i+N-1`, and `change(i-1) <= change_thresh` -> close the current span at `i-1` (`end_next_frame = i`) and start a new one at `i`.
- Spans reaching the last frame: `end_next_frame=None`, `end_next_pts = end_pts + (pts[-1]-pts[-2])` (if only one frame, that frame's pts + 0 is acceptable).
- Dropouts shorter than N frames and glitches shorter than N frames do not split or create spans.

- [ ] **Step 1: Write failing tests** in `tests/test_segment.py` (helper `stats(pixels, changes=None, step=Fraction(1,30))` builds `FrameStat`s; `cfg` N=2, `min_pixels=300`, `change_thresh=0.3`):
  - `test_frame_change`: identical masks -> 0.0; disjoint -> 1.0; both empty -> 0.0; A=100px, B shares 50 + 50 new -> `2/3` approx; `prev=None` -> 0.0.
  - `test_single_event`: `[0]*5+[500]*10+[0]*5` -> one span `start_frame=5, end_frame=14, end_next_frame=15`, `start_pts == 5*step`, `end_next_pts == 15*step`.
  - `test_one_frame_dropout_inside_event_not_split`: `[500]*5+[0]+[500]*5` -> one span 0..10.
  - `test_one_frame_blip_ignored`: `[0]*5+[500]+[0]*5` -> `[]`.
  - `test_back_to_back_replacement`: `[500]*20` with `change[10]=0.8` -> spans (0..9, next 10) and (10..19).
  - `test_one_frame_glitch_not_split`: `change[10]=change[11]=0.8` (glitch at frame 10) -> one span.
  - `test_event_at_frame_zero_and_last_frame`: `[500]*10` -> one span 0..9, `end_next_frame is None`, `end_next_pts == pts9 + step`.
  - `test_vfr_pts_carried`: irregular PTS -> span `start_pts`/`end_next_pts` equal the stats' PTS at those indices.
  - `test_n_equals_one`: `hysteresis_frames=1` makes a one-frame blip a span.
  - `test_empty_input`: `[]` -> `[]`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** `frame_change` and `segment` per the algorithm.
- [ ] **Step 4: Run tests**; expect PASS.
- [ ] **Step 5: Commit** `feat: event segmentation with hysteresis`

---

### Task 6: Temporal fusion

**Files:**
- Create: `subocr/fuse.py`, `tests/test_fuse.py`

**Interfaces:**
- Produces (`subocr/fuse.py`):
  - `pick_sample_indices(start: int, end: int, max_frames: int = 15) -> list[int]` (inclusive range; evenly spaced, includes both ends, strictly increasing, all of them if the range is <= `max_frames`)
  - `fuse(crops: Sequence[np.ndarray], masks: Sequence[np.ndarray]) -> np.ndarray`: grayscale `uint8`, black text on white. Algorithm: per-pixel min of gray crops; stable mask = pixels set in >= 50% of masks, dilated 3 px; output = `255 - where(stable, min_gray, 0)`; padded with a 10 px white border.

- [ ] **Step 1: Write failing tests**:
  - `test_pick_all_when_short`: `pick_sample_indices(10, 19)` == `list(range(10, 20))`.
  - `test_pick_evenly`: `pick_sample_indices(0, 99, 15)` has length 15, first 0, last 99, strictly increasing.
  - `test_pick_single_frame`: `pick_sample_indices(7, 7) == [7]`.
  - `test_fuse_removes_moving_background`: 8 synthetic crops with identical outlined text and a different bright moving blob each; fused image has dark pixels (< 128) at text locations and fewer than 1% non-white pixels outside the text box (plus border offset).
  - `test_fuse_output_contract`: dtype `uint8`, 2-D, border rows are 255.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** with NumPy/OpenCV.
- [ ] **Step 4: Run tests**; expect PASS.
- [ ] **Step 5: Commit** `feat: temporal fusion`

---

### Task 7: OCR adapter (RapidOCR)

**Files:**
- Create: `subocr/ocr.py`, `tests/test_ocr.py`, `tests/fakes.py`

**Interfaces:**
- Produces (`subocr/ocr.py`):
  - `@dataclass(frozen=True) OcrResult(text: str, confidence: float)`
  - `class OcrEngine(Protocol): def read(self, image: np.ndarray) -> OcrResult`
  - `class RapidOcrEngine: __init__(self, lang: str)`; `read` sorts detected boxes top-to-bottom (left-to-right within a line, boxes with > 50% vertical overlap form one line, joined by a space), joins lines with `\n`; confidence = character-count-weighted mean of line scores; returns `OcrResult("", 0.0)` when nothing is found.
  - `make_engine(cfg: OcrCfg) -> OcrEngine` (`ConfigError` for unknown engine names)
- Produces (`tests/fakes.py`): `class FakeEngine(OcrEngine)` taking a list of `OcrResult` returned in call order.

- [ ] **Step 1: Spike (go/no-go).** Render `"¿Qué haces, niño? Está aquí."` with PIL (black on white, 40 px) and run it through RapidOCR with the Latin/Spanish recognition model (consult the installed `rapidocr` docs for how to select it; models download on first use). Record the exact config used and the output in `README.md` under "OCR notes". **If accented letters (á é í ó ú ñ ¿ ¡) are not recognised, stop and report to the user before continuing.**
- [ ] **Step 2: Write failing tests**:
  - `test_fake_engine_returns_in_order`.
  - `test_make_engine_unknown_raises` -> `ConfigError`.
  - `@pytest.mark.slow test_rapidocr_reads_rendered_spanish`: two-line image (`"¿Qué haces?"` over `"Nada, niño."`) -> `result.text` equals `"¿Qué haces?\nNada, niño."` after stripping whitespace (allow `.lower()` and punctuation-insensitive compare only if the spike showed the model drops them; record that in the test comment), `result.confidence > 0.6`.
  - `@pytest.mark.slow test_rapidocr_blank_image`: all-white image -> `OcrResult("", 0.0)`.
  - Register `slow` marker in `pyproject.toml`; default `pytest` run excludes it via `-m "not slow"` in `addopts`.
- [ ] **Step 3: Run** `.venv/bin/pytest tests/test_ocr.py -v -m "not slow"`; fast tests FAIL, then implement.
- [ ] **Step 4: Implement** `ocr.py`. Run `.venv/bin/pytest tests/test_ocr.py -m slow -v`; expect PASS.
- [ ] **Step 5: Commit** `feat: OCR adapter`

---

### Task 8: Post-processing

**Files:**
- Create: `subocr/post.py`, `tests/test_post.py`

**Interfaces:**
- Consumes: `Event` (Task 2), `PostCfg`, `OcrCfg` (Task 1).
- Produces: `clean_events(events: Sequence[Event], post: PostCfg, min_confidence: float) -> list[Event]`. Order: (1) drop empty text; (2) drop UI noise (full-text match of `ui_regex`, or blocklist match, case-insensitive, whitespace-stripped); (3) merge adjacent events with `rapidfuzz.fuzz.ratio(a,b)/100 >= merge_similarity` and `next.start_frame - cur.end_frame - 1 <= merge_max_gap_frames` (merged keeps first `start_*`, last `end_*`/`end_next_*`, text and confidence of the higher-confidence event); (4) drop events with `end_frame - start_frame + 1 < min_event_frames`; (5) renumber ids from 1; (6) `needs_review = confidence < min_confidence` (never drops).

- [ ] **Step 1: Write failing tests** (events built by a small helper):
  - `test_drops_empty_and_ui_noise`: `""`, `"12:34"`, `"1:02:03"`, `"skip intro"`, `"SALTAR INTRO"` dropped; `"Hola."` kept.
  - `test_merge_similar_adjacent`: `"Hola, qué tal"` + `"Hola, que tal"`, gap 1 frame -> one event, start of first, end of last, text of the higher-confidence one.
  - `test_no_merge_when_gap_3`; `test_no_merge_when_dissimilar`; `test_identical_gap_zero_merges`.
  - `test_short_events_dropped_after_merge`: a 2-frame event is dropped, a 3-frame event kept; two 2-frame fragments of one subtitle merge into a 5-frame event that survives.
  - `test_needs_review_flag`: confidence 0.5 with `min_confidence=0.6` -> kept, `needs_review is True`; 0.6 -> False.
  - `test_ids_renumbered`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** `post.py` (use `dataclasses.replace`).
- [ ] **Step 4: Run tests**; expect PASS.
- [ ] **Step 5: Commit** `feat: post-processing`

---

### Task 9: Pipeline (two-pass) and end-to-end accuracy tests

**Files:**
- Create: `subocr/pipeline.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: everything above.
- Produces (`subocr/pipeline.py`):
  - `@dataclass(frozen=True) RunResult(info: ProbeInfo, n_frames: int, spans: list[Span], events: list[Event])`
  - `run_pipeline(video: Path, cfg: Config, out_dir: Path, engine: OcrEngine, offset: Fraction = Fraction(0), debug_dir: Path | None = None, progress: Callable[[str, int, int | None], None] | None = None) -> RunResult`
    - Pass 1: `iter_frames` -> `roi.crop` -> `make_mask` -> `FrameStat` (`change` via `frame_change` on previous mask), collect all stats -> `segment`.
    - Pass 2: re-decode; for each span collect crops+masks at `pick_sample_indices(start_frame, end_frame, cfg.fusion_max_frames)` (stop decoding after the last needed frame); `fuse` -> `engine.read` -> `Event.from_span`; save debug image if `debug_dir`.
    - Then `clean_events`, and write `events.csv`, `subs.srt`, `frame_index.csv` into `out_dir` (created if missing). Raise `VideoError` if pass 2 frame indices/PTS diverge from pass 1.

- [ ] **Step 1: Write failing tests** (use `synth_config`, `FakeEngine`; default 30 fps 640x360, lossless):
  - `test_boundaries_exact_frames`: subs at (30..89), (120..179), (180..239 back-to-back, different text), (300..N-1 reaching the last frame), and (0..9 at frame 0 in a second spec) -> `result.spans` start/end frames equal the spec exactly (tolerance 0), `end_next_frame` correct, `None` for the last.
  - `test_no_subtitles_outputs`: `subs=[]` -> `events == []`, `events.csv` has only a header, `subs.srt` empty, `frame_index.csv` has `n_frames + 1` lines.
  - `test_ui_clutter_makes_no_events`: `cursor=True, progress_bar=True, subs=[]` -> no spans.
  - `test_ui_clutter_does_not_break_real_event`: same clutter with one subtitle -> exactly one span with exact frames.
  - `test_vfr_timestamps_from_pts`: `vfr_drop_every=7` with one subtitle -> event `end_next_pts - start_pts` equals the difference of the written PTS values at those frames (exact `Fraction` equality), not `frames/fps`.
  - `test_offset_applied_in_outputs`: `offset=Fraction(1)` shifts SRT/CSV times, not frame numbers.
  - `test_debug_images_written`: `debug_dir` gets `event_0001.png`.
  - `test_events_text_and_review_flags`: `FakeEngine` low-confidence result -> `needs_review` True in CSV.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_pipeline.py -v`; expect FAIL.
- [ ] **Step 3: Implement** `pipeline.py`. If `test_boundaries_exact_frames` fails by a frame, debug segmentation/mask thresholds on the synthetic video before relaxing anything; the ±0 tolerance on lossless synthetic video is the bar.
- [ ] **Step 4: Run the whole suite** `.venv/bin/pytest -v`; expect PASS.
- [ ] **Step 5: Commit** `feat: two-pass pipeline`

---

### Task 10: CLI, sample command, README

**Files:**
- Create: `subocr/cli.py`, `tests/test_cli.py`, `README.md`

**Interfaces:**
- Consumes: `probe`, `iter_frames`, `build_roi`, `make_mask`, `run_pipeline`, `make_engine`, `load_config`.
- Produces (`subocr/cli.py`, `app = typer.Typer()`):
  - `subocr probe VIDEO`: prints resolution, codec, `r_frame_rate`, `avg_frame_rate`, time_base, duration, frames; prints a `WARNING: variable frame rate...` line if VFR.
  - `subocr sample VIDEO --every 30s --out DIR [--config FILE]`: `--every` accepts `30s`, `1m`, `90` (seconds); for each sample time (by PTS) writes `sample_NNN_full.png` (full frame with ROI and exclusion rectangles drawn), `sample_NNN_roi.png`, `sample_NNN_mask.png`.
  - `subocr run VIDEO --out DIR [--config FILE] [--engine rapidocr] [--offset 12.345] [--debug-dir DIR]`: runs `run_pipeline` with a progress bar; prints a summary (events, needs_review count, output paths) and the VFR warning.
  - `parse_every(text: str) -> Fraction` (public helper). All `ProbeError`/`VideoError`/`ConfigError` become `Error: <message>` on stderr, exit code 1.

- [ ] **Step 1: Write failing tests** (typer `CliRunner`):
  - `test_parse_every`: `"30s"`->30, `"1m"`->60, `"90"`->90, `"abc"` raises `ValueError`.
  - `test_probe_command_vfr_warning`: VFR synth file output contains `WARNING` and the width `640`.
  - `test_sample_writes_three_files_per_sample`: 3-second spec, `--every 1s` -> 3 samples x 3 files.
  - `test_run_with_fake_engine`: monkeypatch `subocr.cli.make_engine` to return `FakeEngine`; `run` exits 0 and writes `events.csv`, `subs.srt`, `frame_index.csv`.
  - `test_errors_are_one_line`: nonexistent video exits 1, stderr starts with `Error:`, no `Traceback`; bad `--offset abc` same.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement `cli.py`**; write `README.md`: Fedora setup (`uv venv --python 3.12`, install), recommended OBS settings (constant 60 fps, low CRF / high bitrate), the tuning workflow (`probe` -> `sample` -> adjust `config.yaml` ROI/exclusions/`v_min`/`s_max` -> `run`), offset semantics, output column reference, boundary definitions, deferred features list, the OCR notes from Task 7.
- [ ] **Step 4: Run** `.venv/bin/pytest -v` (all) and `.venv/bin/pytest -m slow -v`; expect PASS. Then `.venv/bin/subocr --help` lists the three commands.
- [ ] **Step 5: Commit** `feat: CLI and README`

---

## Self-review notes

- Spec coverage: probe/VFR warning (T3, T10), PTS (T3, T9), ROI+exclusions+sample helper (T4, T10), outline mask (T4), segmentation+hysteresis+boundaries (T5), fusion (T6), OCR (T7), post (T8), CSV/SRT/debug/frame index (T2, T9), offset (T2, T9, T10), tests on synthetic frames and formatting (T2, T5, T9). Deferred per spec: `box`, speed mode, Tesseract, `compare`, `--to-cfr`, shot-change stats, `boundary_uncertain`, correction UI, `.exe`, **fade handling** (added to the deferred list because the XOR/OR change metric would split a fading subtitle; decide on real video).
- Type names used across tasks: `FrameStat`, `Span`, `Event`, `Roi`, `OcrResult`, `OcrEngine`, `RunResult` are defined once in Interfaces and reused unchanged.
- Commit steps assume `git init` from Task 1; skip them if you prefer.
