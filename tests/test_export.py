import csv
from fractions import Fraction as F
from pathlib import Path

import cv2
import numpy as np
import pytest

from subocr.export import (
    format_srt_time, format_ts, write_csv, write_debug_image, write_frame_index, write_srt,
)
from subocr.models import Event, FrameStat, Span


def ev(id=1, sf=90, ef=149, nf=150, sp=F(3), ep=F(149, 30), np_=F(5), text="Hola", conf=0.9, review=False):
    return Event(id, sf, ef, nf, sp, ep, np_, text, conf, review)


def read_csv(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def test_format_srt_time():
    assert format_srt_time(F(3661) + F(1, 2)) == "01:01:01,500"
    assert format_srt_time(F(1, 2000)) == "00:00:00,001"
    assert format_srt_time(F(1, 3)) == "00:00:00,333"
    assert format_srt_time(F(599996, 10000)) == "00:01:00,000"
    with pytest.raises(ValueError):
        format_srt_time(F(-1, 10))


def test_format_ts_uses_dot():
    assert format_ts(F(3661) + F(1, 2)) == "01:01:01.500"


def test_from_span():
    s = Span(1, 2, 3, F(1), F(2), F(3))
    e = Event.from_span(7, s, "x", 0.5)
    assert (e.id, e.start_frame, e.end_next_pts, e.text, e.confidence, e.needs_review) == (7, 1, F(3), "x", 0.5, False)


def test_srt_multiline_and_accents(tmp_path: Path):
    p = tmp_path / "a.srt"
    write_srt(p, [ev(text="¿Qué haces?\nNada, niño.", sp=F(3), np_=F(5))])
    raw = p.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    # CRLF on every platform (conventional for SRT), so Linux and Windows write identical files
    assert raw.decode("utf-8") == "1\r\n00:00:03,000 --> 00:00:05,000\r\n¿Qué haces?\r\nNada, niño.\r\n\r\n"


def test_csv_roundtrip_hostile_text(tmp_path: Path):
    p = tmp_path / "e.csv"
    text = 'a,b\n"c", ¡hola!'
    write_csv(p, [ev(text=text)])
    row = read_csv(p)[0]
    assert row["text"] == text
    assert row["start_frame"] == "90" and row["end_frame"] == "149" and row["end_next_frame"] == "150"
    assert float(row["duration_s"]) == 2.0
    assert row["end_ts"] == "00:00:05.000" and row["start_ts"] == "00:00:03.000"
    assert row["n_lines"] == "2"
    n_chars = len(text.replace("\n", ""))
    assert int(row["n_chars"]) == n_chars
    assert float(row["cps"]) == pytest.approx(n_chars / 2.0, abs=0.06)
    assert row["start_pts"] == "3/1" and row["end_next_pts"] == "5/1"


def test_csv_columns_order(tmp_path: Path):
    p = tmp_path / "e.csv"
    write_csv(p, [ev()])
    header = p.read_text(encoding="utf-8-sig").splitlines()[0]
    assert header == ("id,start_frame,end_frame,end_next_frame,start_ts,end_ts,duration_s,text,"
                      "n_lines,n_chars,cps,confidence,needs_review,start_pts,end_pts,end_next_pts")


def test_csv_end_next_none_blank(tmp_path: Path):
    p = tmp_path / "e.csv"
    write_csv(p, [ev(nf=None)])
    assert read_csv(p)[0]["end_next_frame"] == ""


def test_offset_shifts_and_skips(tmp_path: Path):
    events = [ev(1, sp=F(3), np_=F(5)), ev(2, 0, 10, 11, F(0), F(10, 30), F(1))]
    srt = tmp_path / "a.srt"
    write_srt(srt, events, offset=F(3, 2))
    text = srt.read_text(encoding="utf-8")
    assert "00:00:01,500 --> 00:00:03,500" in text
    assert text.count("-->") == 1  # second event ends before the offset -> skipped
    csv_p = tmp_path / "e.csv"
    write_csv(csv_p, events, offset=F(3, 2))
    rows = read_csv(csv_p)
    assert len(rows) == 2 and rows[1]["start_frame"] == "0"


def test_empty_outputs(tmp_path: Path):
    write_csv(tmp_path / "e.csv", [])
    write_srt(tmp_path / "a.srt", [])
    assert len((tmp_path / "e.csv").read_text(encoding="utf-8-sig").splitlines()) == 1
    assert (tmp_path / "a.srt").read_text() == ""


def test_frame_index_and_debug_image(tmp_path: Path):
    stats = [FrameStat(i, F(i, 30), 0, 0.0) for i in range(3)]
    p = tmp_path / "frame_index.csv"
    write_frame_index(p, stats)
    lines = p.read_text().splitlines()
    assert lines[0] == "index,pts,pts_s" and len(lines) == 4 and lines[2].startswith("1,1/30,")
    out = write_debug_image(tmp_path / "dbg", 7, np.full((10, 20), 255, np.uint8))
    assert out.name == "event_0007.png" and cv2.imread(str(out)) is not None
