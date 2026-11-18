"""Write a short synthetic video with two subtitles, for smoke-testing a built app: make_smoke_video.py OUT.mp4"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from synth import SynthSpec, SynthSub, write_video  # noqa: E402

if __name__ == "__main__":
    out = Path(sys.argv[1])
    write_video(out, SynthSpec(n_frames=120, subs=[
        SynthSub(20, 50, ("Hola, ¿qué tal?",)),
        SynthSub(70, 100, ("Nada de nada, amigo.",)),
    ]))
    print(out)
