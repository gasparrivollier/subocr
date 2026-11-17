"""Configuration dataclasses and YAML loading."""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


class ConfigError(Exception):
    """Invalid or unreadable configuration."""


@dataclass(frozen=True)
class Rect:
    top: float
    bottom: float
    left: float
    right: float


@dataclass(frozen=True)
class MaskCfg:
    strategy: str = "outline"
    v_min: int = 200
    s_max: int = 60
    require_outline: bool = True
    dark_v_max: int = 60
    outline_radius_px: int = 3
    max_stroke_px: int = 12
    open_px: int = 1
    close_px: int = 3


@dataclass(frozen=True)
class SegCfg:
    min_pixels: int = 300
    change_thresh: float = 0.3
    hysteresis_frames: int = 2


@dataclass(frozen=True)
class OcrCfg:
    engine: str = "rapidocr"
    lang: str = "es"
    min_confidence: float = 0.6


@dataclass(frozen=True)
class PostCfg:
    merge_similarity: float = 0.9
    merge_max_gap_frames: int = 2
    min_event_frames: int = 3
    blocklist: tuple[str, ...] = ("Skip intro", "Saltar intro")
    ui_regex: str = r"^\d{1,2}:\d{2}(:\d{2})?$"


@dataclass(frozen=True)
class Config:
    roi: Rect = Rect(0.65, 1.0, 0.0, 1.0)
    exclude: tuple[Rect, ...] = ()
    mask: MaskCfg = field(default_factory=MaskCfg)
    segmentation: SegCfg = field(default_factory=SegCfg)
    ocr: OcrCfg = field(default_factory=OcrCfg)
    post: PostCfg = field(default_factory=PostCfg)
    fusion_max_frames: int = 15


def _build(cls, data: Any, where: str):
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise ConfigError(f"'{where}' must be a mapping")
    names = {f.name for f in dataclasses.fields(cls)}
    unknown = set(data) - names
    if unknown:
        raise ConfigError(f"unknown or not-yet-supported option(s) in '{where}': {', '.join(sorted(unknown))}")
    return cls(**data)


def _rect(data: Any, where: str, base: Rect | None = None) -> Rect:
    if not isinstance(data, dict):
        raise ConfigError(f"'{where}' must be a mapping")
    unknown = set(data) - {"top", "bottom", "left", "right"}
    if unknown:
        raise ConfigError(f"unknown option(s) in '{where}': {', '.join(sorted(unknown))}")
    base = base or Rect(0.0, 1.0, 0.0, 1.0)
    r = dataclasses.replace(base, **data)
    for name in ("top", "bottom", "left", "right"):
        v = getattr(r, name)
        if not isinstance(v, (int, float)) or not 0.0 <= v <= 1.0:
            raise ConfigError(f"'{where}.{name}' must be a number between 0 and 1, got {v!r}")
    if r.top >= r.bottom or r.left >= r.right:
        raise ConfigError(f"'{where}' is empty: top must be < bottom and left < right")
    return r


def load_config(path: Path | None) -> Config:
    if path is None:
        return Config()
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except OSError as e:
        raise ConfigError(f"cannot read config file {path}: {e.strerror or e}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {path}: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError("config file must contain a mapping at the top level")
    allowed = {"roi", "exclude", "mask", "segmentation", "ocr", "post", "fusion_max_frames"}
    unknown = set(raw) - allowed
    if unknown:
        raise ConfigError(f"unknown or not-yet-supported option(s): {', '.join(sorted(unknown))}")

    default = Config()
    roi = _rect(raw["roi"], "roi", default.roi) if "roi" in raw else default.roi
    exclude = tuple(_rect(r, f"exclude[{i}]") for i, r in enumerate(raw.get("exclude") or []))
    mask = _build(MaskCfg, raw.get("mask"), "mask")
    if mask.strategy != "outline":
        raise ConfigError(f"mask strategy '{mask.strategy}' is not available yet (only 'outline')")
    post_data = dict(raw.get("post") or {})
    if "blocklist" in post_data:
        post_data["blocklist"] = tuple(post_data["blocklist"])
    return Config(
        roi=roi,
        exclude=exclude,
        mask=mask,
        segmentation=_build(SegCfg, raw.get("segmentation"), "segmentation"),
        ocr=_build(OcrCfg, raw.get("ocr"), "ocr"),
        post=_build(PostCfg, post_data, "post"),
        fusion_max_frames=raw.get("fusion_max_frames", default.fusion_max_frames),
    )
