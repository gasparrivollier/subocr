import dataclasses
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from subocr.config import Config, Rect, SegCfg  # noqa: E402


@pytest.fixture
def synth_config() -> Config:
    """Config tuned for the 640x360 synthetic video: progress strip excluded."""
    base = Config()
    return dataclasses.replace(
        base,
        roi=Rect(0.65, 1.0, 0.0, 1.0),
        exclude=(Rect(0.955, 0.995, 0.0, 1.0),),
        segmentation=SegCfg(min_pixels=250, change_thresh=0.3, hysteresis_frames=2),
    )
