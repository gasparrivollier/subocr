import pytest

from subocr.app.assets import ASSET_NAMES, load_animation


def test_all_assets_load_square():
    for name in ASSET_NAMES:
        anim = load_animation(name)
        assert anim.frames and len(anim.frames) == len(anim.delays_ms)
        assert all(f.size == (160, 160) and f.mode == "RGB" for f in anim.frames)


def test_gif_frame_counts():
    assert len(load_animation("sleeping").frames) == 10
    assert len(load_animation("working").frames) == 33
    assert all(d >= 40 for d in load_animation("working").delays_ms)


def test_stills_single_frame():
    for name in ("done", "error"):
        anim = load_animation(name)
        assert len(anim.frames) == 1 and anim.delays_ms == [0]


def test_size_parameter():
    assert load_animation("done", 96).frames[0].size == (96, 96)


def test_unknown_name_raises():
    with pytest.raises(KeyError):
        load_animation("nope")
