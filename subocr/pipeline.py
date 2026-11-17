"""Two-pass pipeline: scan every frame -> spans; re-decode sampled frames -> fuse -> OCR -> clean -> export."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Callable

import cv2

from .config import Config
from .export import write_csv, write_debug_image, write_frame_index, write_srt
from .fuse import fuse, pick_sample_indices
from .masks import make_mask
from .models import Event, FrameStat, Span
from .ocr import OcrEngine
from .post import clean_events
from .probe import ProbeInfo, probe
from .roi import build_roi
from .segment import frame_change, segment
from .video import VideoError, iter_frames

Progress = Callable[[str, int, "int | None"], None]


@dataclass(frozen=True)
class RunResult:
    info: ProbeInfo
    n_frames: int
    spans: list[Span]
    events: list[Event]


def run_pipeline(video: Path, cfg: Config, out_dir: Path, engine: OcrEngine,
                 offset: Fraction = Fraction(0), debug_dir: Path | None = None,
                 progress: Progress | None = None) -> RunResult:
    report = progress or (lambda stage, done, total: None)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    info = probe(video)
    roi = build_roi(cfg, info.width, info.height)

    # ---- pass 1: every frame -> mask stats
    stats: list[FrameStat] = []
    prev = None
    for fr in iter_frames(video):
        mask = make_mask(roi.crop(fr.image), roi.ignore, cfg.mask)
        stats.append(FrameStat(fr.index, fr.pts, int(mask.sum()), frame_change(prev, mask)))
        prev = mask
        if fr.index % 100 == 0:
            report("scanning", fr.index, info.n_frames)
    spans = segment(stats, cfg.segmentation)

    # ---- pass 2: sampled frames of each span -> fused image -> OCR (one span in memory at a time)
    samples = [pick_sample_indices(s.start_frame, s.end_frame, cfg.fusion_max_frames) for s in spans]
    owner = {i: k for k, idx in enumerate(samples) for i in idx}
    crops: dict[int, list] = {}
    masks: dict[int, list] = {}
    raw: list[Event] = []
    tmp_images: dict[int, Path] = {}
    if spans:
        last_needed = max(owner)
        for fr in iter_frames(video):
            if fr.pts != stats[fr.index].pts:
                raise VideoError("the video decoded differently on the second pass; cannot continue")
            k = owner.get(fr.index)
            if k is not None:
                crop = roi.crop(fr.image).copy()
                crops.setdefault(k, []).append(crop)
                masks.setdefault(k, []).append(make_mask(crop, roi.ignore, cfg.mask))
                if fr.index == samples[k][-1]:
                    fused = fuse(crops.pop(k), masks.pop(k))
                    res = engine.read(fused)
                    raw.append(Event.from_span(k + 1, spans[k], res.text, res.confidence))
                    if debug_dir is not None:
                        tmp_images[spans[k].start_frame] = write_debug_image(
                            Path(debug_dir), 100000 + k + 1, fused)
                    report("reading text", len(raw), len(spans))
            if fr.index >= last_needed:
                break

    events = clean_events(raw, cfg.post, cfg.ocr.min_confidence)

    # ---- debug images: rename to the final event ids, drop those of discarded spans
    if debug_dir is not None:
        final = {}
        for e in events:
            src = tmp_images.get(e.start_frame)
            if src is not None:
                final[src] = Path(debug_dir) / f"event_{e.id:04d}.png"
        for src in tmp_images.values():
            if src not in final:
                src.unlink(missing_ok=True)
        for src, dst in final.items():
            src.replace(dst)

    write_csv(out_dir / "events.csv", events, offset)
    write_srt(out_dir / "subs.srt", events, offset)
    write_frame_index(out_dir / "frame_index.csv", stats)
    report("done", len(stats), len(stats))
    return RunResult(info, len(stats), spans, events)
