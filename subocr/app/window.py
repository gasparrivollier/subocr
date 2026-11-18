"""The Snoopy window (PySide6). Thin: all logic lives in AppModel/Job; this only draws the ViewState."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional

from PIL import Image
from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter, QPainterPath, QPixmap, QTextOption
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QProgressBar,
                               QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from .assets import ASSET_NAMES, load_animation
from .model import AppModel, State, ViewState
from .paths import reveal_in_folder

IMAGE_FOR_STATE = {State.START: "sleeping", State.WORKING: "working", State.DONE: "done", State.ERROR: "error"}
VIDEO_FILTER = "Video files (*.mp4 *.mkv *.mov *.avi *.webm *.m4v);;All files (*)"

STYLE = """
QWidget#root { background: #f3f4f6; }
QLabel { color: #1b1b1b; font-size: 13px; }
QLabel#title { font-size: 18px; font-weight: 600; }
QLabel#title[tone="ok"] { color: #107c10; }
QLabel#title[tone="err"] { color: #c42b1c; }
QLabel#status { color: #5b6270; }
QLabel#percent { color: #5b6270; font-size: 12px; }
QPlainTextEdit#path { background: #ffffff; border: 1px solid #d3d7de; border-radius: 6px; padding: 7px 9px;
              font-family: Consolas, 'DejaVu Sans Mono', monospace; font-size: 11px; color: #2b2f36; }
QFrame#right[dropzone="true"] { border: 2px dashed #9aa3b0; border-radius: 12px; background: #fafbfc; }
QPushButton { background: #e6e9ee; border: 1px solid #c5cad2; border-radius: 7px; padding: 9px 20px; font-size: 13px; }
QPushButton:hover { background: #dbdfe6; }
QPushButton#primary { background: #0067c0; color: #ffffff; border: 1px solid #0067c0; font-weight: 600; }
QPushButton#primary:hover { background: #005aa8; }
QProgressBar { border: none; background: #d9dde3; border-radius: 7px; min-height: 14px; max-height: 14px; }
QProgressBar::chunk { background: #0067c0; border-radius: 7px; }
"""


def to_pixmap(img: Image.Image, radius: int = 14) -> QPixmap:
    w, h = img.size
    qimg = QImage(img.convert("RGB").tobytes("raw", "RGB"), w, h, w * 3, QImage.Format.Format_RGB888).copy()
    out = QPixmap(w, h)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    painter.setClipPath(path)
    painter.drawImage(0, 0, qimg)
    painter.end()
    return out


def _ask_file() -> Optional[Path]:
    name, _ = QFileDialog.getOpenFileName(None, "Choose a video", "", VIDEO_FILTER)
    return Path(name) if name else None


class App(QWidget):
    def __init__(self, model: AppModel | None = None, pick_file: Callable[[], Optional[Path]] | None = None,
                 reveal: Callable[[Path], None] = reveal_in_folder):
        super().__init__()
        self.model = model or AppModel()
        self.pick_file = pick_file or _ask_file
        self.reveal = reveal
        self.setObjectName("root")
        self.setWindowTitle("Subtitle extractor")
        self.setFixedSize(600, 320)
        self.setAcceptDrops(True)
        self.setStyleSheet(STYLE)

        self._pixmaps: dict[str, list[QPixmap]] = {}
        self._delays: dict[str, list[int]] = {}
        for name in ASSET_NAMES:
            anim = load_animation(name, 176)
            self._pixmaps[name] = [to_pixmap(f) for f in anim.frames]
            self._delays[name] = anim.delays_ms
        self._playing: Optional[str] = None
        self._frame_index = 0
        self._signature: Optional[tuple] = None

        outer = QHBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(22)
        self.image_label = QLabel()
        self.image_label.setFixedSize(176, 176)
        outer.addWidget(self.image_label, 0, Qt.AlignmentFlag.AlignTop)

        self.right = QFrame()
        self.right.setObjectName("right")
        col = QVBoxLayout(self.right)
        col.setContentsMargins(14, 12, 14, 12)
        col.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("title")
        self.title_label.setWordWrap(True)
        self.status_label = QLabel()
        self.status_label.setObjectName("status")
        self.status_label.setWordWrap(True)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.percent_label = QLabel()
        self.percent_label.setObjectName("percent")
        self.path_label = QPlainTextEdit()  # wraps anywhere, so long Windows paths stay readable and selectable
        self.path_label.setObjectName("path")
        self.path_label.setReadOnly(True)
        self.path_label.setFixedHeight(62)
        self.path_label.setFrameShape(QFrame.Shape.NoFrame)
        self.path_label.setWordWrapMode(QTextOption.WrapMode.WrapAnywhere)
        self.path_label.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.path_label.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.primary_button = QPushButton()
        self.primary_button.setObjectName("primary")
        self.secondary_button = QPushButton()
        self._primary_action: Callable[[], None] = lambda: None
        self._secondary_action: Callable[[], None] = lambda: None
        self.primary_button.clicked.connect(lambda: self._primary_action())
        self.secondary_button.clicked.connect(lambda: self._secondary_action())
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(self.primary_button)
        row.addWidget(self.secondary_button)
        row.addStretch(1)
        for w in (self.title_label, self.status_label, self.progress, self.percent_label, self.path_label):
            col.addWidget(w)
        col.addStretch(1)
        col.addLayout(row)
        outer.addWidget(self.right, 1)

        self._anim_timer = QTimer(self)
        self._anim_timer.setSingleShot(True)
        self._anim_timer.timeout.connect(self._show_frame)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self.refresh)
        self.refresh()
        self._tick_timer.start(100)

    # ---- actions
    def _choose(self) -> None:
        video = self.pick_file()
        if video is not None:
            self.model.choose(video)
            self.refresh()

    def _reset(self) -> None:
        self.model.reset()
        self.refresh()

    def _handle_drop(self, path: Path) -> None:
        if path.is_file():
            self.model.choose(path)  # ignored by the model while a job is running
            self.refresh()

    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.mimeData().hasUrls() and self.model.view.state is not State.WORKING:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            if url.isLocalFile():
                self._handle_drop(Path(url.toLocalFile()))
                break

    def _on_close(self) -> None:
        self._tick_timer.stop()
        self._anim_timer.stop()
        self.model.shutdown()

    def closeEvent(self, event) -> None:  # noqa: N802
        self._on_close()
        event.accept()

    # ---- drawing
    def refresh(self) -> None:
        v = self.model.tick()
        self.progress.setValue(v.percent)
        self.percent_label.setText(f"{v.percent}%")
        if v.state is State.WORKING:
            self.status_label.setText(v.stage)
        signature = (v.state, v.video, v.message, v.srt_path, v.log_path, v.n_subtitles)
        if signature != self._signature:
            self._signature = signature
            self._render(v)

    def _set_title(self, text: str, tone: str = "") -> None:
        self.title_label.setText(text)
        self.title_label.setProperty("tone", tone)
        self.title_label.style().unpolish(self.title_label)
        self.title_label.style().polish(self.title_label)

    def _render(self, v: ViewState) -> None:
        dropzone = v.state is State.START
        self.right.setProperty("dropzone", dropzone)
        self.right.style().unpolish(self.right)
        self.right.style().polish(self.right)
        for w in (self.progress, self.percent_label, self.path_label, self.secondary_button):
            w.setVisible(False)
        if v.state is State.START:
            self._set_title("Drag a video here")
            self.status_label.setText("or choose one from your computer.\nWorks with screen recordings of subtitled video (mp4, mkv, mov…).")
            self.primary_button.setText("Choose video…")
            self._primary_action = self._choose
        elif v.state is State.WORKING:
            name = v.video.name if v.video else ""
            bold = QFont(self.title_label.font())
            bold.setPixelSize(18)
            bold.setBold(True)  # measure with the real title font, or the text would not fit
            self._set_title(QFontMetrics(bold).elidedText(name, Qt.TextElideMode.ElideMiddle, 280))
            self.title_label.setToolTip(name)
            self.status_label.setText(v.stage)
            self.progress.setVisible(True)
            self.percent_label.setVisible(True)
            self.primary_button.setText("Cancel")
            self._primary_action = self.model.cancel
        elif v.state is State.DONE:
            if v.n_subtitles == 0:
                self._set_title(v.message or "No subtitles were found in this video.")
            else:
                s = "" if v.n_subtitles == 1 else "s"
                self._set_title(f"Done: {v.n_subtitles} subtitle{s} found", "ok")
            self.status_label.setText("Your subtitle file is here:")
            self.path_label.setPlainText(str(v.srt_path))
            self.path_label.setVisible(True)
            self.primary_button.setText("Show in folder")
            self._primary_action = lambda: self.reveal(v.srt_path)
            self.secondary_button.setText("Another video")
            self._secondary_action = self._reset
            self.secondary_button.setVisible(True)
        else:
            self._set_title("Something went wrong", "err")
            self.status_label.setText(v.message)
            self.path_label.setPlainText(str(v.log_path))
            self.path_label.setVisible(True)
            self.primary_button.setText("Show log")
            self._primary_action = lambda: self.reveal(v.log_path)
            self.secondary_button.setText("Try another")
            self._secondary_action = self._reset
            self.secondary_button.setVisible(True)
        self._play(IMAGE_FOR_STATE[v.state])

    def _play(self, name: str) -> None:
        self._anim_timer.stop()
        self._playing = name
        self._frame_index = 0
        self._show_frame()

    def _show_frame(self) -> None:
        name = self._playing
        if name is None:
            return
        frames, delays = self._pixmaps[name], self._delays[name]
        self.image_label.setPixmap(frames[self._frame_index])
        if len(frames) > 1:
            delay = delays[self._frame_index]
            self._frame_index = (self._frame_index + 1) % len(frames)
            self._anim_timer.start(delay)


def run() -> None:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    window = App()
    window.show()
    app.exec()
