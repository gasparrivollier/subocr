from fractions import Fraction as F

from subocr.config import PostCfg
from subocr.models import Event
from subocr.post import clean_events

POST = PostCfg()


def ev(text, sf, ef, conf=0.95, id=1):
    return Event(id, sf, ef, ef + 1, F(sf, 30), F(ef, 30), F(ef + 1, 30), text, conf)


def clean(events, min_conf=0.6):
    return clean_events(events, POST, min_conf)


def test_drops_empty_and_ui_noise():
    kept = clean([ev("", 0, 20), ev("12:34", 30, 50), ev("1:02:03", 60, 80), ev("skip intro", 90, 110),
                  ev("SALTAR INTRO", 120, 140), ev("Hola.", 150, 170)])
    assert [e.text for e in kept] == ["Hola."]


def test_drops_events_without_a_real_word():
    # spinner / button junk like "C 11 6"; real one-word subtitles stay
    kept = clean([ev("C 11 6", 0, 20), ev("Sí.", 30, 50), ev("¡Ay!", 60, 80)])
    assert [e.text for e in kept] == ["Sí.", "¡Ay!"]


def test_merge_similar_adjacent():
    a, b = ev("Hola, qué tal", 0, 30, 0.9), ev("Hola, que tal", 32, 60, 0.95)
    out = clean([a, b])
    assert len(out) == 1
    e = out[0]
    assert (e.start_frame, e.end_frame, e.end_next_frame) == (0, 60, 61)
    assert e.start_pts == F(0) and e.end_next_pts == F(61, 30)
    assert e.text == "Hola, que tal" and e.confidence == 0.95


def test_no_merge_when_gap_3():
    assert len(clean([ev("Hola, qué tal", 0, 30), ev("Hola, qué tal", 34, 60)])) == 2


def test_no_merge_when_dissimilar():
    assert len(clean([ev("Hola, qué tal", 0, 30), ev("Nada de nada", 31, 60)])) == 2


def test_identical_gap_zero_merges():
    assert len(clean([ev("Hola, qué tal", 0, 30), ev("Hola, qué tal", 31, 60)])) == 1


def test_short_events_dropped_after_merge():
    assert clean([ev("Hola, qué tal", 0, 1)]) == []
    assert len(clean([ev("Hola, qué tal", 0, 2)])) == 1
    merged = clean([ev("Hola, qué tal", 0, 1), ev("Hola, qué tal", 3, 4)])
    assert len(merged) == 1 and merged[0].end_frame - merged[0].start_frame + 1 == 5


def test_needs_review_flag():
    low, ok = clean([ev("Hola, qué tal", 0, 30, 0.5), ev("Nada de nada", 40, 70, 0.6)])
    assert low.needs_review is True and ok.needs_review is False


def test_ids_renumbered():
    out = clean([ev("", 0, 10, id=5), ev("Hola, qué tal", 20, 50, id=6), ev("Nada de nada", 60, 90, id=7)])
    assert [e.id for e in out] == [1, 2]
