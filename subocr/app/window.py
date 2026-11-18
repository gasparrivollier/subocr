"""The Snoopy window. Thin: all logic lives in AppModel/Job, this only draws the current ViewState."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Callable, Optional

from PIL import ImageTk

from .assets import ASSET_NAMES, load_animation
from .model import AppModel, State, ViewState
from .paths import reveal_in_folder

VIDEO_TYPES = [("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"), ("All files", "*.*")]
IMAGE_FOR_STATE = {State.START: "sleeping", State.WORKING: "working", State.DONE: "done", State.ERROR: "error"}


def _ask_file() -> Optional[Path]:
    name = filedialog.askopenfilename(title="Choose a video", filetypes=VIDEO_TYPES)
    return Path(name) if name else None


class App(tk.Tk):
    def __init__(self, model: AppModel | None = None, pick_file: Callable[[], Optional[Path]] | None = None,
                 reveal: Callable[[Path], None] = reveal_in_folder):
        super().__init__()
        self.model = model or AppModel()
        self.pick_file = pick_file or _ask_file
        self.reveal = reveal
        self.title("Subtitle extractor")
        self.geometry("520x300")
        self.resizable(False, False)

        self._photos: dict[str, list[ImageTk.PhotoImage]] = {}
        self._delays: dict[str, list[int]] = {}
        for name in ASSET_NAMES:
            anim = load_animation(name)
            self._photos[name] = [ImageTk.PhotoImage(f, master=self) for f in anim.frames]
            self._delays[name] = anim.delays_ms
        self._playing: Optional[str] = None
        self._anim_after: Optional[str] = None
        self._signature: Optional[tuple] = None

        body = ttk.Frame(self, padding=18)
        body.pack(fill="both", expand=True)
        self.image_label = ttk.Label(body)
        self.image_label.pack(side="left", padx=(0, 16))
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        self.title_label = ttk.Label(right, font=("TkDefaultFont", 12, "bold"), wraplength=290, justify="left")
        self.title_label.pack(anchor="w", pady=(0, 6))
        self.status_label = ttk.Label(right, wraplength=290, justify="left")
        self.status_label.pack(anchor="w", pady=(0, 6))
        self.progress = ttk.Progressbar(right, length=280, maximum=100, mode="determinate")
        self.percent_label = ttk.Label(right)
        self.path_label = ttk.Label(right, wraplength=290, justify="left", font=("TkFixedFont", 9))
        buttons = ttk.Frame(right)
        buttons.pack(side="bottom", anchor="w", pady=(10, 0))
        self.primary_button = ttk.Button(buttons)
        self.primary_button.pack(side="left", padx=(0, 8))
        self.secondary_button = ttk.Button(buttons)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.refresh()
        self._schedule_tick()

    # ---- actions
    def _choose(self) -> None:
        video = self.pick_file()
        if video is not None:
            self.model.choose(video)
            self.refresh()

    def _reset(self) -> None:
        self.model.reset()
        self.refresh()

    def _on_close(self) -> None:
        self.model.shutdown()
        if self._anim_after is not None:
            self.after_cancel(self._anim_after)
        self.destroy()

    # ---- drawing
    def _schedule_tick(self) -> None:
        self._tick_after = self.after(100, self._tick)

    def _tick(self) -> None:
        self.refresh()
        self._schedule_tick()

    def refresh(self) -> None:
        v = self.model.tick()
        self.progress["value"] = v.percent
        self.percent_label.configure(text=f"{v.percent}%")
        if v.state is State.WORKING:
            self.status_label.configure(text=v.stage)
        signature = (v.state, v.video, v.message, v.srt_path, v.log_path, v.n_subtitles)
        if signature != self._signature:
            self._signature = signature
            self._render(v)

    def _render(self, v: ViewState) -> None:
        for w in (self.progress, self.percent_label, self.path_label, self.secondary_button):
            w.pack_forget()
        if v.state is State.START:
            self.title_label.configure(text="Choose a video to extract its subtitles")
            self.status_label.configure(text="Works with screen recordings of subtitled video (mp4, mkv, mov…).")
            self.primary_button.configure(text="Choose video…", command=self._choose)
        elif v.state is State.WORKING:
            self.title_label.configure(text=v.video.name if v.video else "")
            self.status_label.configure(text=v.stage)
            self.progress.pack(anchor="w", pady=(0, 4))
            self.percent_label.pack(anchor="w")
            self.primary_button.configure(text="Cancel", command=self.model.cancel)
        elif v.state is State.DONE:
            if v.n_subtitles == 0:
                self.title_label.configure(text=v.message or "No subtitles were found in this video.")
            else:
                s = "" if v.n_subtitles == 1 else "s"
                self.title_label.configure(text=f"Done: {v.n_subtitles} subtitle{s} found")
            self.status_label.configure(text="Your subtitle file is here:")
            self.path_label.configure(text=str(v.srt_path))
            self.path_label.pack(anchor="w", pady=(0, 4))
            self.primary_button.configure(text="Show in folder", command=lambda: self.reveal(v.srt_path))
            self.secondary_button.configure(text="Another video", command=self._reset)
            self.secondary_button.pack(side="left")
        else:
            self.title_label.configure(text="Something went wrong")
            self.status_label.configure(text=v.message)
            self.path_label.configure(text=str(v.log_path))
            self.path_label.pack(anchor="w", pady=(0, 4))
            self.primary_button.configure(text="Show log", command=lambda: self.reveal(v.log_path))
            self.secondary_button.configure(text="Try another", command=self._reset)
            self.secondary_button.pack(side="left")
        self._play(IMAGE_FOR_STATE[v.state])

    def _play(self, name: str) -> None:
        if self._anim_after is not None:
            self.after_cancel(self._anim_after)
            self._anim_after = None
        self._playing = name
        self._frame_index = 0
        self._show_frame()

    def _show_frame(self) -> None:
        name = self._playing
        if name is None:
            return
        frames, delays = self._photos[name], self._delays[name]
        self.image_label.configure(image=frames[self._frame_index])
        if len(frames) > 1:
            delay = delays[self._frame_index]
            self._frame_index = (self._frame_index + 1) % len(frames)
            self._anim_after = self.after(delay, self._show_frame)


def run() -> None:
    App().mainloop()
