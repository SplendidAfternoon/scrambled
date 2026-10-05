"""Open the plugin editor in a host (pedalboard) and save renders of it to plugin/docs/.

Uses the editor's SE_UI_SNAPSHOT hook (the UI reads back its own OpenGL frame), so it also works on a
locked or headless desktop where screen capture returns black. SE_UI_T pins the time cursor (echo step) and
SE_UI_TIME the animation clock so the shots are reproducible.

    .venv\\Scripts\\python plugin\\tools\\screenshot_ui.py [name ...]
"""
import os
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pedalboard
from PIL import Image

PLUGIN = Path(__file__).resolve().parents[1]
VST3 = PLUGIN / "dist" / "ScrambledEcho.vst3" / "Contents" / "x86_64-win" / "ScrambledEcho.vst3"
DOCS = PLUGIN / "docs"
TMP = PLUGIN / "build"


def shoot(p, out, t=24.0, clock=3.0, view=None, wait=12.0):
    p.process(np.zeros((2, 512), np.float32), 48000, reset=False)  # pedalboard applies parameter changes here
    ppm = TMP / (out.stem + ".ppm")
    ppm.unlink(missing_ok=True)
    os.environ["SE_UI_SNAPSHOT"] = os.fspath(ppm)
    os.environ["SE_UI_T"] = str(t)
    os.environ["SE_UI_TIME"] = str(clock)
    if view:
        os.environ["SE_UI_VIEW"] = view
    else:
        os.environ.pop("SE_UI_VIEW", None)
    close = threading.Event()

    def watch():
        t0 = time.time()
        last = -1
        while time.time() - t0 < wait:
            if ppm.exists():
                size = ppm.stat().st_size
                if size > 0 and size == last:
                    break
                last = size
            time.sleep(0.3)
        close.set()

    threading.Thread(target=watch, daemon=True).start()
    p.show_editor(close)
    if ppm.exists() and ppm.stat().st_size > 0:
        Image.open(ppm).save(out)
        print("saved", out.relative_to(PLUGIN))
    else:
        print("no snapshot for", out.name)


def reset(p):
    p.split = 0.0
    for s in range(12):
        setattr(p, f"site_{s}_split", 0.0)
        setattr(p, f"site_{s}_gain_db", 0.0)


SHOTS = {}


def shot(fn):
    SHOTS[fn.__name__] = fn
    return fn


@shot
def ui_whole(p):
    reset(p)
    p.map = "Scrambling"
    p.scramble = 0.0
    shoot(p, DOCS / "ui_whole.png", t=24)


@shot
def ui_shattered(p):
    reset(p)
    p.map = "Scrambling"
    p.scramble = 100.0
    shoot(p, DOCS / "ui_shattered.png", t=24)


@shot
def ui_light_cone(p):
    reset(p)
    p.map = "Edge kick, sparse (site 0)"
    p.scramble = 100.0
    shoot(p, DOCS / "ui_light_cone.png", t=12)


@shot
def ui_split(p):
    reset(p)
    p.map = "Scrambling"
    p.scramble = 70.0
    for s, (split, gain) in {2: (85.0, 3.0), 3: (55.0, 0.0), 9: (70.0, -12.0)}.items():
        setattr(p, f"site_{s}_split", split)
        setattr(p, f"site_{s}_gain_db", gain)
    shoot(p, DOCS / "ui_split.png", t=20, view="yaw=0.35;pitch=0.22;zoom=0.92;sel=-1")


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    p = pedalboard.load_plugin(os.fspath(VST3))
    names = sys.argv[1:] or list(SHOTS)
    for n in names:
        SHOTS[n](p)
