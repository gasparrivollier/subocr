from pathlib import Path

import pytest

from subocr.config import ConfigError, Rect, load_config


def test_defaults_match_spec():
    cfg = load_config(None)
    assert cfg.roi == Rect(0.65, 1.0, 0.0, 1.0)
    assert cfg.segmentation.min_pixels == 300
    assert cfg.segmentation.change_thresh == 0.3
    assert cfg.segmentation.hysteresis_frames == 2
    assert cfg.mask.v_min == 200
    assert cfg.mask.s_max == 60
    assert cfg.post.merge_similarity == 0.9
    assert cfg.post.min_event_frames == 3
    assert cfg.ocr.min_confidence == 0.6


def test_partial_yaml_overrides(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("segmentation: {min_pixels: 100}\n")
    cfg = load_config(p)
    assert cfg.segmentation.min_pixels == 100
    assert cfg.segmentation.change_thresh == 0.3


def test_exclude_rects_loaded(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("exclude:\n  - {top: 0.9, bottom: 1.0, left: 0.0, right: 1.0}\n")
    assert load_config(p).exclude == (Rect(0.9, 1.0, 0.0, 1.0),)


def test_unknown_key_raises(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("segmentation: {sample_step: 4}\n")
    with pytest.raises(ConfigError, match="sample_step"):
        load_config(p)


def test_box_strategy_rejected(tmp_path: Path):
    p = tmp_path / "c.yaml"
    p.write_text("mask: {strategy: box}\n")
    with pytest.raises(ConfigError, match="box"):
        load_config(p)


@pytest.mark.parametrize("roi", ["{top: 0.9, bottom: 0.5}", "{top: -0.1}", "{bottom: 1.5}"])
def test_bad_roi_raises(tmp_path: Path, roi: str):
    p = tmp_path / "c.yaml"
    p.write_text(f"roi: {roi}\n")
    with pytest.raises(ConfigError):
        load_config(p)


def test_missing_file_raises(tmp_path: Path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "nope.yaml")
