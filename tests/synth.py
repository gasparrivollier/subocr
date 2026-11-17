"""Synthetic test video: moving noisy background, outlined subtitles, optional UI clutter."""
from __future__ import annotations

from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

TIME_BASE = Fraction(1, 15360)


@dataclass
class SynthSub:
    start: int  # inclusive frame index of the written video
    end: int    # inclusive
    lines: tuple[str, ...]


@dataclass
class SynthSpec:
    subs: list[SynthSub] = field(default_factory=list)
    n_frames: int = 60
    size: tuple[int, int] = (640, 360)
    fps: int = 30
    vfr_drop_every: int = 0   # skip every k-th frame's slot (PTS gap), 0 = CFR
    cursor: bool = False
    progress_bar: bool = False


_FONT_CANDIDATES = [
    "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf",
    "/usr/share/fonts/liberation-sans-fonts/LiberationSans-Bold.ttf",
    "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
]


def _font(size: int = 28) -> ImageFont.FreeTypeFont:
    for name in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    raise RuntimeError("no usable bold TrueType font found for the synthetic video")


def sub_layer(size: tuple[int, int], lines: tuple[str, ...]) -> tuple[np.ndarray, np.ndarray]:
    """Return (rgb, alpha-bool) of the subtitle drawn alone: white fill, black outline."""
    w, h = size
    img = Image.new("RGB", size, (0, 0, 0))
    mask = Image.new("L", size, 0)
    font = _font()
    for k, line in enumerate(lines):
        y = int(h * 0.72) + k * 36
        for target, fill in ((img, (255, 255, 255)), (mask, 255)):
            d = ImageDraw.Draw(target)
            tw = d.textlength(line, font=font)
            d.text(((w - tw) / 2, y), line, font=font, fill=fill, stroke_width=3,
                   stroke_fill=(0, 0, 0) if target is img else 255)
    return np.asarray(img), np.asarray(mask) > 0


def background(spec: SynthSpec, i: int) -> np.ndarray:
    w, h = spec.size
    rng = np.random.default_rng(i)
    xs = (np.arange(w)[None, :] + 3 * i) % w
    base = (40 + 60 * (xs / w) + 20 * np.sin(np.arange(h)[:, None] / 20 + i / 5)).astype(np.float32)
    img = np.repeat(base[:, :, None], 3, axis=2) + rng.normal(0, 3, (h, w, 3))
    # bright moving blob, NO outline (must not count as text)
    cx, cy = int((i * 7) % w), int(h * 0.68)
    yy, xx = np.ogrid[:h, :w]
    blob = ((xx - cx) ** 2 / 40 ** 2 + (yy - cy) ** 2 / 8 ** 2) < 1
    img[blob] = 245
    return np.clip(img, 0, 255).astype(np.uint8)


def render_frame(spec: SynthSpec, i: int, layers: dict[int, tuple[np.ndarray, np.ndarray]]) -> np.ndarray:
    img = background(spec, i)
    w, h = spec.size
    for k, sub in enumerate(spec.subs):
        if sub.start <= i <= sub.end:
            rgb, m = layers[k]
            img[m] = rgb[m]
    pil = Image.fromarray(img)
    d = ImageDraw.Draw(pil)
    if spec.progress_bar:
        d.rectangle([int(w * .05), int(h * .965), int(w * .95), int(h * .985)], fill=(235, 235, 235))
        d.ellipse([int(w * .05) + 2 * i, int(h * .96), int(w * .05) + 2 * i + 12, int(h * .99)], fill=(255, 255, 255))
    if spec.cursor:
        x, y = int((i * 5) % (w - 20)), int(h * 0.66) + (i % 14)
        d.polygon([(x, y), (x, y + 14), (x + 4, y + 11), (x + 10, y + 11)], fill=(255, 255, 255), outline=(0, 0, 0))
    return np.asarray(pil)


def write_video(path: Path, spec: SynthSpec) -> list[Fraction]:
    """Write a lossless H.264 mp4; return the PTS (seconds) of every written frame."""
    layers = {k: sub_layer(spec.size, s.lines) for k, s in enumerate(spec.subs)}
    step = int(round(float(TIME_BASE.denominator) / spec.fps / 1))  # ticks per frame (512 at 30 fps)
    container = av.open(str(path), "w")
    stream = container.add_stream("libx264", rate=spec.fps)
    stream.width, stream.height = spec.size
    stream.pix_fmt = "yuv444p"
    stream.options = {"crf": "0", "preset": "ultrafast"}
    stream.codec_context.time_base = TIME_BASE
    pts_list: list[Fraction] = []
    slot = -1  # first frame at PTS 0
    for i in range(spec.n_frames):
        slot += 1
        if spec.vfr_drop_every and (i + 1) % spec.vfr_drop_every == 0:
            slot += 1  # leave a one-slot hole in the timeline
        frame = av.VideoFrame.from_ndarray(render_frame(spec, i, layers), format="rgb24")
        frame.pts = slot * step
        frame.time_base = TIME_BASE
        for pkt in stream.encode(frame):
            container.mux(pkt)
        pts_list.append(Fraction(frame.pts) * TIME_BASE)
    for pkt in stream.encode():
        container.mux(pkt)
    container.close()
    return pts_list
