import numpy as np
import pytest
from PIL import Image, ImageDraw

from subocr.config import ConfigError, OcrCfg, PostCfg
from subocr.ocr import Detection, OcrResult, assemble_lines, make_engine
from fakes import FakeEngine
from synth import _font

POST = PostCfg()


def d(text, x0, x1, y0, y1, score=0.99):
    return Detection(x0, y0, x1, y1, text, score)


def test_fake_engine_returns_in_order():
    e = FakeEngine([OcrResult("a", 0.9), OcrResult("b", 0.8)])
    assert [e.read(None).text, e.read(None).text] == ["a", "b"]


def test_make_engine_unknown_raises():
    with pytest.raises(ConfigError):
        make_engine(OcrCfg(engine="nope"), POST)


def test_lines_sorted_top_to_bottom_left_to_right():
    r = assemble_lines([d("tal?", 120, 180, 100, 130), d("Segunda", 0, 90, 140, 170), d("Hola", 0, 100, 102, 132)], POST)
    assert r.text == "Hola tal?\nSegunda"


def test_ui_boxes_dropped_before_grouping():
    # "0:00" sits on the same row as the second subtitle line; it must not join that line
    dets = [d("El transbordador", 100, 300, 100, 130), d("0:00", 20, 60, 140, 170),
            d("tiene unos 37 m", 100, 300, 140, 170), d("39:41", 560, 620, 142, 168),
            d("Skip intro", 400, 500, 10, 40)]
    assert assemble_lines(dets, POST).text == "El transbordador\ntiene unos 37 m"


def test_duplicate_word_across_overlapping_boxes_collapsed():
    r = assemble_lines([d("Orbitas el", 0, 100, 100, 130), d("el planeta", 80, 200, 100, 130)], POST)
    assert r.text == "Orbitas el planeta"


def test_repeated_word_in_separate_boxes_kept():
    r = assemble_lines([d("no", 0, 40, 100, 130), d("no", 60, 100, 100, 130)], POST)
    assert r.text == "no no"


def test_confidence_weighted_by_characters():
    r = assemble_lines([d("aaaa", 0, 40, 100, 130, 1.0), d("b", 0, 40, 140, 170, 0.6)], POST)
    assert r.confidence == pytest.approx((4 * 1.0 + 1 * 0.6) / 5)


def test_nothing_detected():
    assert assemble_lines([], POST) == OcrResult("", 0.0)


def _render(lines):
    img = Image.new("L", (900, 60 + 60 * len(lines)), 255)
    dr = ImageDraw.Draw(img)
    for k, t in enumerate(lines):
        dr.text((40, 30 + 60 * k), t, font=_font(40), fill=0)
    return np.asarray(img)


@pytest.mark.slow
def test_rapidocr_reads_rendered_spanish():
    r = make_engine(OcrCfg(), POST).read(_render(["¿Qué haces?", "Nada, niño."]))
    assert r.text == "¿Qué haces?\nNada, niño."
    assert r.confidence > 0.6


@pytest.mark.slow
def test_rapidocr_blank_image():
    assert make_engine(OcrCfg(), POST).read(np.full((100, 400), 255, np.uint8)) == OcrResult("", 0.0)
