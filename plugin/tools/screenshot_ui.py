"""Open the plugin editor in a host (pedalboard) and save renders of it to plugin/docs/.

Uses the editor's SE_UI_SNAPSHOT hook (the UI reads back its own OpenGL frame), so it also works on a
locked or headless desktop where screen capture returns black.

    .venv\\Scripts\\python plugin\\tools\\screenshot_ui.py
"""
import os
import threading
import time
from pathlib import Path

import pedalboard
from PIL import Image

PLUGIN = Path(__file__).resolve().parents[1]
VST3 = PLUGIN / "dist" / "ScrambledEcho.vst3" / "Contents" / "x86_64-win" / "ScrambledEcho.vst3"
DOCS = PLUGIN / "docs"
TMP = PLUGIN / "build"


def shoot(p, out, wait=6.0):
    ppm = TMP / (out.stem + ".ppm")
    ppm.unlink(missing_ok=True)
    os.environ["SE_UI_SNAPSHOT"] = os.fspath(ppm)
    close = threading.Event()

    def watch():
        t0 = time.time()
        while time.time() - t0 < wait:
            if ppm.exists() and ppm.stat().st_size > 0:
                time.sleep(0.5)
                break
            time.sleep(0.1)
        close.set()

    threading.Thread(target=watch, daemon=True).start()
    p.show_editor(close)
    if ppm.exists() and ppm.stat().st_size > 0:
        Image.open(ppm).save(out)
        print("saved", out.relative_to(PLUGIN))
    else:
        print("no snapshot for", out.name)


if __name__ == "__main__":
    DOCS.mkdir(exist_ok=True)
    p = pedalboard.load_plugin(os.fspath(VST3))
    p.map = "Edge kick, sparse (site 0)"
    p.scramble = 100.0
    p.view = "F (echo survives)"
    shoot(p, DOCS / "ui_F.png")
    p.view = "C (operator spread)"
    shoot(p, DOCS / "ui_C.png")
    p.map = "Scrambling"
    p.scramble = 60.0
    p.view = "F (echo survives)"
    p.sync = True
    shoot(p, DOCS / "ui_scrambling_sync.png")
