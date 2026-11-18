# subocr Windows App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-contained Windows app (unzip, double-click) with a small Snoopy-themed window: choose a video, watch progress, find the exported `.srt`, see errors.

**Architecture:** The existing engine (`run_pipeline`) is unchanged except for cooperative cancellation. A pure, display-free layer (`Job` thread + `AppModel` state machine + path/message helpers) drives a thin `tkinter` window. PyInstaller (folder mode) packages it; a GitHub Actions Windows runner builds and smoke-tests the zip.

**Tech Stack:** Python 3.12, `tkinter`, Pillow, PyInstaller, existing `subocr` engine (RapidOCR/ONNX, PyAV), GitHub Actions `windows-latest`.

**Spec:** `docs/superpowers/specs/2026-11-15-subocr-design.md` (sections "Window UI", "UI scope", "Windows packaging"). Read them first.

## Global Constraints

- Window states and copy follow the spec's "Window UI": Start / Working / Done / Error; buttons "Choose video…", "Cancel", "Show in folder", "Another video", "Show log", "Try another"; text "Done: N subtitles found".
- Images (spec): sleeping `source.gif` and typing `snoopy-typing.gif` animated; sunglasses `images.jpg` and screaming `44e94c575003338030172fe7d4193d87.jpg` (crop box `(0, 380, 736, 1180)`) stills; all rendered 160x160, cover-cropped. Sources are in `~/Downloads/`; copy them into `subocr/assets/` as `sleeping.gif`, `working.gif`, `done.jpg`, `error.jpg`.
- Output folder: `<video name>_subtitles/` next to the video, containing `subs.srt`, `events.csv`, `frame_index.csv`. If it exists, use `<video name>_subtitles (2)`, `(3)`... Never overwrite: the user edits the SRT in another program.
- Log file `subocr.log`: in the output folder if it could be created, otherwise in the system temp directory. The Error screen shows its path.
- No network at run time; OCR models and images are bundled. No options in the window; Spanish only.
- The engine's tests (`pytest`, 82 tests) must stay green. GUI tests skip themselves when no display is available (Xvfb is not installed here).
- Drag-and-drop onto the window is DEFERRED (needs Windows-only verification; the button is the main path).
- Python 3.12 venv at `.venv`; Windows-specific code (`explorer /select`) is tested through an injected platform and process runner, not by running Windows.
- Public GitHub repo is acceptable, but creating or pushing it is outward-facing: STOP and ask the user before doing it (Task 8 ends there).

## Review Focus

1. Video path with spaces, accents and `ñ` (Windows users' real paths): output folder, log and SRT all created correctly (Task 2).
2. Re-processing the same video: previous results, possibly hand-edited, must never be overwritten (Task 2).
3. Cancel mid-run: stops promptly, leaves no partial output files and no leftover debug files, window returns to Start (Tasks 1, 3).
4. Video with no subtitles, a non-video file, or a read-only destination: plain-language outcome ("No subtitles were found" is not an error; unreadable file and unwritable folder are errors with a log) (Tasks 1, 2).
5. Worker crash (any unexpected exception) or window closed during a run: window shows the Error state with a log (or exits cleanly), never freezes or leaves the worker running (Tasks 1, 3).

---

### Task 1: Cancellable pipeline and background job

**Files:**
- Modify: `subocr/pipeline.py` (add `Cancelled`, `should_cancel` parameter)
- Create: `subocr/app/__init__.py`, `subocr/app/job.py`, `tests/test_job.py`
- Modify: `tests/test_pipeline.py` (add cancel tests)

**Interfaces:**
- Consumes: `run_pipeline(video, cfg, out_dir, engine, offset, debug_dir, progress)` (existing).
- Produces:
  - `subocr.pipeline.Cancelled(Exception)`; `run_pipeline(..., should_cancel: Callable[[], bool] | None = None)`: checked every 25 frames in pass 1 and before each OCR call; raises `Cancelled`; on cancel no file is left in `out_dir` and temp debug images are removed.
  - `subocr.app.job.JobEvent` frozen dataclass: `kind: Literal["progress","done","error","cancelled"]`, `stage: str = ""`, `percent: int = 0`, `n_subtitles: int = 0`, `srt_path: Path | None = None`, `message: str = ""`, `log_path: Path | None = None`.
  - `class Job`: `__init__(self, video: Path, engine_factory: Callable[[Config], OcrEngine] | None = None)`; `start() -> None`; `cancel() -> None`; `poll() -> list[JobEvent]` (non-blocking drain). Progress mapping: scanning = `0..50 %` (stage `"Scanning frames…"`), reading text = `50..100 %` (stage `f"Reading text… {k} of {n} subtitles"`); unknown frame total keeps percent at 0. Exactly one terminal event (`done`/`error`/`cancelled`) is emitted.
  - Uses Task 2's `unique_output_dir`, `log_path_for`, `friendly_message` (implement Task 2 first or stub them; see Task 2 for signatures — order tasks 2, then 1 if executing strictly bottom-up).

- [ ] **Step 1: Write failing tests** in `tests/test_pipeline.py`:
  - `test_cancel_leaves_no_outputs`: `should_cancel` returns True after 30 calls on the boundaries video -> `Cancelled` raised, `out_dir` empty or absent, no `.png` left in `debug_dir`.
  - `test_cancel_none_is_noop`: default `None` behaves as before (existing tests cover it).
- [ ] **Step 2: Write failing tests** in `tests/test_job.py` (synthetic video, `FakeEngine`):
  - `test_job_done`: events end with `kind="done"`, `n_subtitles == 4`, `srt_path` ends with `subs.srt` inside `<stem>_subtitles/`, percent monotonically non-decreasing and last progress percent <= 100.
  - `test_job_progress_stages`: stages seen include `"Scanning frames…"` and a string matching `Reading text… \d+ of \d+ subtitles`.
  - `test_job_zero_subtitles_is_done_not_error`: video without subtitles -> `done`, `n_subtitles == 0`, `srt_path` exists (empty file).
  - `test_job_non_video_is_error`: text file renamed `.mp4` -> `error`, `message` non-empty and without the word "Traceback", `log_path` exists and contains the exception type.
  - `test_job_cancel`: cancel right after `start()` on a longer video -> terminal `cancelled`, output folder absent or empty.
  - `test_job_unexpected_exception_is_error`: engine factory raises `RuntimeError("boom")` -> `error` event (not a hung thread), log contains `boom`.
  - `test_job_unwritable_destination`: video in a read-only directory (`chmod 0o555`, skip if running as root) -> `error`, message mentions the folder cannot be written.
- [ ] **Step 3: Run** `.venv/bin/pytest tests/test_pipeline.py tests/test_job.py -q`; expect FAIL.
- [ ] **Step 4: Implement** `Cancelled` + `should_cancel` in `pipeline.py` (wrap the body in `try/finally` that removes temp debug images when cancelled or failing; write outputs only at the very end as now) and `Job` (daemon thread, `queue.Queue`, `threading.Event` for cancel; any exception -> log the traceback with `logging` to the log file, emit `error` with `friendly_message(exc)`).
- [ ] **Step 5: Run the full suite** `.venv/bin/pytest -q`; expect PASS (82 existing + new).
- [ ] **Step 6: Commit** `feat: cancellable pipeline and background job`

---

### Task 2: Paths, log and plain-language messages

**Files:**
- Create: `subocr/app/paths.py`, `tests/test_app_paths.py`

**Interfaces:**
- Produces:
  - `unique_output_dir(video: Path) -> Path`: `<video parent>/<stem>_subtitles`, or ` (2)`, ` (3)`… if it exists; does not create it.
  - `log_path_for(video: Path, out_dir: Path | None) -> Path`: `out_dir/subocr.log` if `out_dir` exists or can be created, else `Path(tempfile.gettempdir())/"subocr.log"`.
  - `friendly_message(exc: BaseException) -> str`: `ProbeError`/`VideoError` -> `"This file can't be opened as a video. Try a different file."` (frames without PTS -> a message saying the recording has no usable timestamps); `PermissionError`/`OSError` while writing -> `"The results can't be saved in that folder. Move the video to a folder you can write to."`; `MemoryError` -> `"Not enough memory to process this video."`; anything else -> `"Something unexpected went wrong. Details were saved to the log file."`.
  - `reveal_in_folder(path: Path, platform: str | None = None, runner: Callable[..., Any] = subprocess.Popen) -> None`: Windows (`"win32"`) runs `["explorer", f"/select,{path}"]`; macOS `["open","-R",path]`; Linux `["xdg-open", path.parent]`. `platform=None` uses `sys.platform`.

- [ ] **Step 1: Write failing tests**:
  - `test_unique_output_dir_basic`: `Path("/v/Mi película ñ.mp4")`-style path in `tmp_path` -> `"Mi película ñ_subtitles"`.
  - `test_unique_output_dir_never_reuses`: create `x_subtitles` and `x_subtitles (2)` -> returns `x_subtitles (3)`.
  - `test_log_path_prefers_output_dir` and `test_log_path_falls_back_to_temp` (out_dir is a path under a file, so not creatable).
  - `test_friendly_message_cases`: one assertion per exception type listed above, and that none of the messages contain `"Traceback"`.
  - `test_reveal_in_folder_commands`: fake `runner` records args for `"win32"`, `"darwin"`, `"linux"`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_app_paths.py -q`; expect FAIL.
- [ ] **Step 3: Implement** the four functions.
- [ ] **Step 4: Run** the new tests; expect PASS. **Step 5: Commit** `feat: output folder naming, log path, friendly messages`

---

### Task 3: App state machine

**Files:**
- Create: `subocr/app/model.py`, `tests/test_app_model.py`

**Interfaces:**
- Consumes: `Job`, `JobEvent` (Task 1).
- Produces:
  - `class State(Enum)`: `START, WORKING, DONE, ERROR`.
  - `@dataclass(frozen=True) ViewState(state: State, video: Path | None = None, stage: str = "", percent: int = 0, message: str = "", srt_path: Path | None = None, log_path: Path | None = None, n_subtitles: int = 0)`.
  - `class AppModel`: `__init__(job_factory: Callable[[Path], Job] = Job)`; `view: ViewState` (property); `choose(video: Path) -> None` (START/DONE/ERROR -> WORKING, starts the job); `tick() -> ViewState` (drains `job.poll()`, applies events, returns the view); `cancel() -> None` (asks the job to cancel; the view returns to START when the `cancelled` event arrives); `reset() -> None` (DONE/ERROR -> START); `shutdown() -> None` (cancels any running job and waits briefly; safe to call twice).
  - `DONE` message for 0 subtitles: `message = "No subtitles were found in this video."` (not an error state).

- [ ] **Step 1: Write failing tests** with a fake job (scripted events):
  - `test_start_to_working_to_done`: states and fields after each `tick()`.
  - `test_zero_subtitles_message`.
  - `test_error_state_keeps_log_path`.
  - `test_cancel_returns_to_start`.
  - `test_choose_ignored_while_working`.
  - `test_reset_from_done_and_error`.
  - `test_shutdown_cancels_running_job_and_is_idempotent`.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Implement** `model.py`. **Step 4: Run** expect PASS. **Step 5: Commit** `feat: app state machine`

---

### Task 4: Assets and animation frames

**Files:**
- Create: `subocr/assets/` (four copied images), `subocr/app/assets.py`, `tests/test_app_assets.py`
- Modify: `pyproject.toml` (add `pillow` to dependencies; package data `subocr/assets/*`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Animation(frames: list[PIL.Image.Image], delays_ms: list[int])`
  - `ASSET_NAMES = ("sleeping", "working", "done", "error")`
  - `load_animation(name: str, size: int = 160) -> Animation`: resolves files via `importlib.resources.files("subocr") / "assets"`; every frame is RGB and exactly `size x size` after centre-cover cropping (error image first cropped to `(0,380,736,1180)`); stills have one frame and delay `0`; gif delays come from the file (min 40 ms); unknown name -> `KeyError`.

- [ ] **Step 1: Copy** `~/Downloads/source.gif` -> `subocr/assets/sleeping.gif`, `snoopy-typing.gif` -> `working.gif`, `images.jpg` -> `done.jpg`, `44e94c575003338030172fe7d4193d87.jpg` -> `error.jpg`; list the folder and confirm 4 files.
- [ ] **Step 2: Write failing tests**: `test_all_assets_load_square` (every name returns frames of size `(160,160)`, mode `RGB`); `test_gif_frame_counts` (`sleeping` has 10 frames, `working` has 33); `test_stills_single_frame`; `test_size_parameter` (`load_animation("done", 96)` is 96x96); `test_unknown_name_raises`.
- [ ] **Step 3: Run** expect FAIL. **Step 4: Implement** `assets.py` (Pillow `ImageSequence`, `ImageOps.fit` for cover cropping). **Step 5: Run** expect PASS. **Step 6: Commit** `feat: Snoopy assets and animation loader`

---

### Task 5: tkinter window and entry point

**Files:**
- Create: `subocr/app/window.py`, `subocr/app/__main__.py`, `tests/test_app_window.py`

**Interfaces:**
- Consumes: `AppModel`, `ViewState`, `State` (Task 3); `load_animation` (Task 4); `reveal_in_folder` (Task 2).
- Produces:
  - `class App(tk.Tk)`: `__init__(self, model: AppModel | None = None, pick_file: Callable[[], Path | None] | None = None, reveal: Callable[[Path], None] = reveal_in_folder)`; `refresh() -> None` (applies `model.tick()` to widgets; also scheduled every 100 ms with `after`); widgets are attributes the tests read: `title_label`, `status_label`, `progress`, `path_label`, `primary_button`, `secondary_button`, `image_label`.
  - `main(argv: list[str] | None = None) -> int`: no arguments opens the window (title "Subtitle extractor", fixed ~520x300, closing the window calls `model.shutdown()`); `--selftest VIDEO OUTDIR` runs the real pipeline headless with the real OCR engine and prints one JSON line `{"events": N, "srt": "<path>"}` (exit 0) or `{"error": "..."}` (exit 1).
- State -> widgets (from the spec): START: sleeping gif, "Choose video…" (primary button, calls `pick_file` then `model.choose`); WORKING: working gif, file name, `status_label` = stage, bar = percent, "Cancel"; DONE: `done` still, "Done: N subtitles found" (or the zero-subtitles message), full `.srt` path, "Show in folder" + "Another video"; ERROR: `error` still, message, log path, "Show log" (reveals the log) + "Try another". GIFs animate via `after(delay)`.

- [ ] **Step 1: Write failing tests** (marked `gui`; skip if `tkinter.Tk()` raises `TclError`; use a scripted fake model):
  - `test_start_screen`: primary button text `"Choose video…"`, image label has an image.
  - `test_working_screen_shows_stage_and_percent`.
  - `test_done_screen_shows_path_and_buttons`; `test_done_zero_subtitles_text`.
  - `test_error_screen_shows_log_path_and_show_log_reveals_it` (fake `reveal` records the path).
  - `test_close_calls_shutdown`.
  - Non-GUI, runs everywhere: `test_selftest_json` calls `main(["--selftest", video, outdir])` with a monkeypatched engine factory and checks the JSON line and exit code; `test_selftest_missing_file_exit_1`.
- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_app_window.py -q`; expect GUI tests FAIL (or SKIP if no display; in that case state so in the ledger) and non-GUI FAIL.
- [ ] **Step 3: Implement** `window.py`/`__main__.py` (use `ttk`; keep references to `ImageTk.PhotoImage` objects so they are not garbage-collected).
- [ ] **Step 4: Run** `.venv/bin/pytest -q`; expect PASS. If a display exists, also launch `.venv/bin/python -m subocr.app` once, pick `the real sample video` and capture a screenshot of each state for the user; otherwise say it was not run.
- [ ] **Step 5: Commit** `feat: Snoopy window and entry point`

---

### Task 6: Packaging recipe (PyInstaller, tested on Linux as a dry run)

**Files:**
- Create: `packaging/subocr_app.spec`, `packaging/make_smoke_video.py`, `packaging/README.md`
- Modify: `pyproject.toml` (extra `build = ["pyinstaller"]`)

**Interfaces:**
- Produces:
  - `packaging/make_smoke_video.py OUT.mp4`: writes a short synthetic video with two subtitles (reuses `tests/synth.py`), used by CI and by this task.
  - `packaging/subocr_app.spec`: folder-mode build named `subocr`, windowed (`console=False`), entry `subocr/app/__main__.py`; collects `rapidocr` data files (models), `subocr/assets`, `onnxruntime` and `av` binaries and `tkinter` data; includes all hidden imports needed.

- [ ] **Step 1: Warm and check the models.** Run `.venv/bin/python -c "from rapidocr import RapidOCR; RapidOCR()"`, then list `site-packages/rapidocr/models/*.onnx`; record whether the wheel ships them or they are downloaded on first use (the CI step in Task 7 must warm them before building).
- [ ] **Step 2: Build on Linux as a dry run:** `uv pip install --python .venv/bin/python -e ".[build]"`, then `.venv/bin/pyinstaller packaging/subocr_app.spec --noconfirm`. Expected: `dist/subocr/` exists; size recorded.
- [ ] **Step 3: Smoke test the bundle, offline:** `.venv/bin/python packaging/make_smoke_video.py /tmp/smoke.mp4`, then `unshare -rn dist/subocr/subocr --selftest /tmp/smoke.mp4 /tmp/smoke_out` (no network namespace). Expected: JSON line with `"events": 2` and exit code 0. If `unshare` is unavailable, run it with the network blocked another way and say what was done. Failure here means models or libraries are not bundled: fix the spec, do not skip.
- [ ] **Step 4: Record** the Linux dry-run size and time in `packaging/README.md`, with the Windows build command (`pyinstaller packaging/subocr_app.spec --noconfirm`) and the user-facing note about the SmartScreen "More info -> Run anyway" screen.
- [ ] **Step 5: Commit** `feat: PyInstaller packaging recipe` (do not commit `build/` or `dist/`; add them to `.gitignore`).

---

### Task 7: GitHub Actions Windows build workflow

**Files:**
- Create: `.github/workflows/build-windows.yml`, `tests/test_workflow.py`

**Interfaces:**
- Produces: workflow `Build Windows app`, triggers `workflow_dispatch` and tags `v*`; job on `windows-latest`: checkout, `actions/setup-python` 3.12, `pip install -e ".[dev,build]"`, `pytest -q`, warm the OCR models (command from Task 6 Step 1), `pyinstaller packaging/subocr_app.spec --noconfirm`, generate the smoke video, run `dist\subocr\subocr.exe --selftest smoke.mp4 smoke_out` and fail unless the JSON shows 2 events, zip `dist/subocr` as `subocr-windows.zip`, upload as artifact, and attach it to the GitHub release on tag builds.

- [ ] **Step 1: Write failing test** `tests/test_workflow.py`: parses the YAML with `yaml.safe_load` and asserts it runs on `windows-latest`, uses Python `3.12`, contains steps that run `pytest`, `pyinstaller`, `--selftest` and upload an artifact, and triggers on tags `v*` and `workflow_dispatch`.
- [ ] **Step 2: Run** expect FAIL. **Step 3: Write the workflow.** **Step 4: Run** `.venv/bin/pytest -q`; expect PASS.
- [ ] **Step 5: Commit** `ci: Windows build workflow`.
- [ ] **Step 6: STOP and ask the user** to approve creating the public GitHub repo and pushing (name, visibility). Do not create or push anything before an explicit yes. After the first Actions run, report the real result (success, artifact size, or failure log) to the user; fixes to the workflow are expected on the first run.

---

### Task 8: User guide

**Files:**
- Modify: `README.md`; Create: `packaging/USER_GUIDE.md`

- [ ] **Step 1: Write** `packaging/USER_GUIDE.md` (plain language, Spanish and English): download the zip, unzip, double-click `subocr.exe`, what the four screens mean, where results are, what to do on the Windows "protected your PC" screen ("More info -> Run anyway"), what `subocr.log` is for, known limits (black-screen footage with white subtitles; Spanish only; the SRT is not edited by the app).
- [ ] **Step 2: Update** `README.md` with the app, the build instructions and a pointer to the guide.
- [ ] **Step 3: Run** `.venv/bin/pytest -q`; expect PASS. **Step 4: Commit** `docs: user guide and README`

---

## Self-review notes

- Spec coverage: four window states + images (T4, T5), no options/Spanish only (T5), output folder + never overwrite + log (T2), progress/cancel/errors (T1, T3), offline bundling + PyInstaller folder mode (T6), GitHub Actions build (T7), user guide and SmartScreen note (T8). Drag-and-drop is deferred (stated in Global Constraints); the "estimated time left" from the mockup is omitted (spec said only if reliable).
- Dependencies between tasks: Task 1 needs Task 2's helpers, so execute 2 before 1 (ordering note in Task 1).
- Names used across tasks (`Job`, `JobEvent`, `AppModel`, `ViewState`, `State`, `Animation`, `load_animation`, `unique_output_dir`, `log_path_for`, `friendly_message`, `reveal_in_folder`) are defined once and reused unchanged.
- The first Actions run may need fixes; that is expected and reported, not hidden.
