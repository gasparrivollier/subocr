"""Command line: subocr probe | sample | run."""
from __future__ import annotations

import dataclasses
import functools
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Optional

import cv2
import typer

from .config import Config, ConfigError, load_config
from .masks import make_mask
from .ocr import make_engine
from .pipeline import run_pipeline
from .probe import ProbeError, probe as probe_video
from .roi import build_roi
from .video import VideoError, iter_frames

app = typer.Typer(add_completion=False, help="Extract burned-in subtitles from a screen recording.")


def fail(message: str) -> "typer.Exit":
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(1)


def friendly_errors(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (ProbeError, VideoError, ConfigError, ValueError) as e:
            raise fail(str(e)) from e
    return wrapper


def parse_every(text: str) -> Fraction:
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([sm]?)\s*", text)
    if not m:
        raise ValueError(f"--every must look like 30s, 1m or 90 (seconds), got '{text}'")
    return Fraction(m.group(1)) * (60 if m.group(2) == "m" else 1)


def parse_offset(text: str) -> Fraction:
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        raise ValueError(f"--offset must be a number of seconds, e.g. 12.345, got '{text}'") from None


def _vfr_warning(info) -> str:
    return ("WARNING: variable frame rate detected "
            f"(r_frame_rate {float(info.r_frame_rate):.3f} vs average {float(info.avg_frame_rate):.3f}). "
            "Timestamps come from each frame's PTS, so results stay exact, but frame counts will not match 'time x fps'.")


@app.command()
@friendly_errors
def probe(video: Path):
    """Show resolution, frame rates and whether the file is variable frame rate."""
    info = probe_video(video)
    typer.echo(f"Resolution:      {info.width}x{info.height}")
    typer.echo(f"Codec:           {info.codec}")
    typer.echo(f"r_frame_rate:    {float(info.r_frame_rate):.3f}")
    typer.echo(f"avg_frame_rate:  {float(info.avg_frame_rate):.3f}")
    typer.echo(f"time_base:       {info.time_base}")
    typer.echo(f"Duration:        {info.duration_s:.2f}s" if info.duration_s else "Duration:        unknown")
    typer.echo(f"Frames:          {info.n_frames if info.n_frames else 'unknown'}")
    if info.is_vfr:
        typer.echo(_vfr_warning(info))


@app.command()
@friendly_errors
def sample(video: Path,
           out: Path = typer.Option(..., help="Folder for the sample images"),
           every: str = typer.Option("30s", help="Interval, e.g. 30s, 1m, 90"),
           config: Optional[Path] = typer.Option(None, help="YAML config (to preview its ROI and mask)")):
    """Save full frames, the ROI crop and the text mask, to tune the ROI and exclusions by eye."""
    step = parse_every(every)
    if step <= 0:
        raise ValueError("--every must be greater than zero")
    cfg = load_config(config)
    info = probe_video(video)
    roi = build_roi(cfg, info.width, info.height)
    out.mkdir(parents=True, exist_ok=True)
    next_t, n = Fraction(0), 0
    for fr in iter_frames(video):
        if fr.pts < next_t:
            continue
        n += 1
        next_t += step
        crop = roi.crop(fr.image)
        full = fr.image.copy()
        x0, y0, x1, y1 = roi.box
        cv2.rectangle(full, (x0, y0), (x1 - 1, y1 - 1), (0, 255, 0), 2)
        for e in cfg.exclude:
            cv2.rectangle(full, (round(e.left * info.width), round(e.top * info.height)),
                          (round(e.right * info.width) - 1, round(e.bottom * info.height) - 1), (0, 0, 255), 2)
        mask = make_mask(crop, roi.ignore, cfg.mask)
        cv2.imwrite(str(out / f"sample_{n:03d}_full.png"), full)
        cv2.imwrite(str(out / f"sample_{n:03d}_roi.png"), crop)
        cv2.imwrite(str(out / f"sample_{n:03d}_mask.png"), mask.astype("uint8") * 255)
    typer.echo(f"Saved {n} sample(s) to {out} (green = ROI, red = excluded areas)")


@app.command()
@friendly_errors
def run(video: Path,
        out: Path = typer.Option(..., help="Folder for events.csv, subs.srt, frame_index.csv"),
        config: Optional[Path] = typer.Option(None, help="YAML config"),
        engine: Optional[str] = typer.Option(None, help="OCR engine (default: rapidocr)"),
        offset: str = typer.Option("0", help="Seconds to subtract: episode_time = recording_time - offset"),
        debug_dir: Optional[Path] = typer.Option(None, help="Save the fused image of each event here")):
    """Extract subtitles: events.csv, subs.srt and frame_index.csv."""
    off = parse_offset(offset)
    cfg: Config = load_config(config)
    if engine:
        cfg = dataclasses.replace(cfg, ocr=dataclasses.replace(cfg.ocr, engine=engine))
    info = probe_video(video)
    if info.is_vfr:
        typer.echo(_vfr_warning(info), err=True)

    last = {"pct": -10}

    def progress(stage: str, done: int, total: Optional[int]) -> None:
        if total:
            pct = int(100 * done / total)
            if pct >= last["pct"] + 10 or stage == "done":
                last["pct"] = pct
                sys.stderr.write(f"\r{stage}: {pct}%   ")
                if stage == "done":
                    sys.stderr.write("\n")
                sys.stderr.flush()

    result = run_pipeline(video, cfg, out, make_engine(cfg.ocr, cfg.post), off, debug_dir, progress)
    n = len(result.events)
    review = sum(e.needs_review for e in result.events)
    typer.echo(f"Found {n} event{'s' if n != 1 else ''} ({review} need review) in {result.n_frames} frames.")
    typer.echo(f"Wrote {out / 'events.csv'}, {out / 'subs.srt'}, {out / 'frame_index.csv'}")


if __name__ == "__main__":
    app()
