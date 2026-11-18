from pathlib import Path

from subocr.app.paths import friendly_message, log_path_for, reveal_in_folder, unique_output_dir
from subocr.config import ConfigError
from subocr.probe import ProbeError
from subocr.video import VideoError


def test_unique_output_dir_basic(tmp_path: Path):
    video = tmp_path / "Mi película ñ.mp4"
    assert unique_output_dir(video) == tmp_path / "Mi película ñ_subtitles"


def test_unique_output_dir_never_reuses(tmp_path: Path):
    (tmp_path / "x_subtitles").mkdir()
    (tmp_path / "x_subtitles (2)").mkdir()
    assert unique_output_dir(tmp_path / "x.mp4") == tmp_path / "x_subtitles (3)"


def test_unique_output_dir_does_not_create(tmp_path: Path):
    unique_output_dir(tmp_path / "x.mp4")
    assert list(tmp_path.iterdir()) == []


def test_log_path_prefers_output_dir(tmp_path: Path):
    out = tmp_path / "out"
    assert log_path_for(tmp_path / "x.mp4", out) == out / "subocr.log"
    assert out.is_dir()


def test_log_path_falls_back_to_temp(tmp_path: Path):
    blocker = tmp_path / "file"
    blocker.write_text("x")
    p = log_path_for(tmp_path / "x.mp4", blocker / "sub")  # cannot create a folder under a file
    assert p.name == "subocr.log" and p.parent != blocker / "sub"


def test_friendly_message_cases():
    cases = {
        "can't be opened as a video": ProbeError("nope"),
        "can't be saved": PermissionError("denied"),
        "memory": MemoryError(),
        "unexpected": RuntimeError("boom"),
    }
    for needle, exc in cases.items():
        msg = friendly_message(exc)
        assert needle in msg and "Traceback" not in msg
    assert "can't be opened as a video" in friendly_message(FileNotFoundError("gone"))
    assert "timestamps" in friendly_message(VideoError("frame 3 has no timestamp (PTS); cannot ..."))
    assert friendly_message(ConfigError("bad")).startswith("The settings")


def test_reveal_in_folder_commands(tmp_path: Path):
    calls = []
    f = tmp_path / "a" / "subs.srt"
    reveal_in_folder(f, "win32", calls.append)
    reveal_in_folder(f, "darwin", calls.append)
    reveal_in_folder(f, "linux", calls.append)
    assert calls == [["explorer", f"/select,{f}"], ["open", "-R", str(f)], ["xdg-open", str(f.parent)]]
