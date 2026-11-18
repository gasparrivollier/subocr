"""Snoopy images for the four window states, as square RGB frames."""
from __future__ import annotations

from dataclasses import dataclass
from importlib import resources

from PIL import Image, ImageOps, ImageSequence

ASSET_NAMES = ("sleeping", "working", "done", "error")
_FILES = {"sleeping": "sleeping.gif", "working": "working.gif", "done": "done.jpg", "error": "error.jpg"}
_CROPS = {"error": (0, 380, 736, 1180)}  # tight on the head and tape
_MIN_DELAY_MS = 40


@dataclass(frozen=True)
class Animation:
    frames: list[Image.Image]
    delays_ms: list[int]  # 0 for stills


def _square(img: Image.Image, size: int, crop: tuple[int, int, int, int] | None) -> Image.Image:
    rgba = img.convert("RGBA")
    flat = Image.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, mask=rgba.split()[3])
    if crop:
        flat = flat.crop(crop)
    return ImageOps.fit(flat, (size, size), Image.LANCZOS)  # cover: fill the square, crop the overflow


def load_animation(name: str, size: int = 160) -> Animation:
    filename = _FILES[name]  # KeyError for unknown names
    path = resources.files("subocr") / "assets" / filename
    with resources.as_file(path) as p, Image.open(p) as im:
        crop = _CROPS.get(name)
        if filename.endswith(".gif"):
            frames, delays = [], []
            for frame in ImageSequence.Iterator(im):
                delays.append(max(int(frame.info.get("duration", 100)), _MIN_DELAY_MS))
                frames.append(_square(frame, size, crop))
            return Animation(frames, delays)
        return Animation([_square(im, size, crop)], [0])
