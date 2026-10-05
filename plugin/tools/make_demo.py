"""Render plugin/docs/ui_demo.mp4: the egg editor reacting to audio, with that audio rendered through the VST3.

1. A parameter/camera script (one row per video frame) and a dry clap/drum input are written to build/demo/.
2. The editor is opened in pedalboard with SE_UI_DEMO=build/demo: it steps through the script offline, runs
   each frame's slice of audio through its own copy of the DSP core (for the tap telemetry) and saves a frame.
3. The same script automates the VST3 (pedalboard, one block per frame) to render the wet audio.
4. ffmpeg muxes frames + audio.

    .venv\\Scripts\\python plugin\\tools\\make_demo.py
"""
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pedalboard
import soundfile as sf
from PIL import Image

PLUGIN = Path(__file__).resolve().parents[1]
VST3 = PLUGIN / "dist" / "ScrambledEcho.vst3" / "Contents" / "x86_64-win" / "ScrambledEcho.vst3"
WORK = PLUGIN / "build" / "demo"
OUT = PLUGIN / "docs" / "ui_demo.mp4"
SR, FPS = 48000, 24
SECONDS = 18.0
BLOCK = SR // FPS


def smooth(a, b, x):
    x = min(1.0, max(0.0, x))
    x = x * x * (3 - 2 * x)
    return a + (b - a) * x


def script(names, map_labels):
    """Parameter values per frame, by pedalboard name, plus camera (yaw, pitch, zoom)."""
    rows = []
    for k in range(int(SECONDS * FPS)):
        t = k / FPS
        v = dict(map=map_labels.index("Edge kick, sparse (site 0)"), sync=0, time_ms=1500.0, division=2,
                 mix=50.0, feedback=25.0, scramble=100.0, width=100.0, view=0, split=0.0)
        for s in range(12):
            v[f"site_{s}_split"] = 0.0
            v[f"site_{s}_gain_db"] = 0.0
        yaw, pitch, zoom = 0.55, 0.18, 1.0
        if t >= 4.5:   # measured scrambling map: Scramble from Control to fully scrambled
            v["map"] = map_labels.index("Scrambling")
            v["scramble"] = smooth(0.0, 100.0, (t - 5.0) / 3.0)
        if t >= 9.0:   # drag site 2 out and up, then site 9 out and down
            v["site_2_split"] = smooth(0.0, 85.0, (t - 9.0) / 1.5)
            v["site_2_gain_db"] = smooth(0.0, 4.0, (t - 9.0) / 1.5)
            v["site_9_split"] = smooth(0.0, 65.0, (t - 11.0) / 1.5)
            v["site_9_gain_db"] = smooth(0.0, -12.0, (t - 11.0) / 1.5)
        if t >= 13.0:  # orbit the camera, then pull the Split macro
            yaw = smooth(0.55, 2.2, (t - 13.0) / 4.0)
            pitch = smooth(0.18, 0.32, (t - 13.0) / 4.0)
            v["split"] = smooth(0.0, 35.0, (t - 15.0) / 2.0)
        rows.append(([float(v[n]) for n in names], (yaw, pitch, zoom)))
    return rows


def dry_input():
    clap = sf.read(PLUGIN / "examples" / "04_clap_control_vs_scrambling_dry.wav", dtype="float32")[0]
    clap = clap.T if clap.ndim == 2 else np.stack([clap, clap])
    # take the first clap and place it every 1.75 s (one hit per echo train at Time 1.5 s)
    env = np.abs(clap).sum(axis=0)
    start = int(np.argmax(env > env.max() * 0.05))
    hit = clap[:, start:start + int(0.35 * SR)] * 0.9
    n = int(SECONDS * SR)
    x = np.zeros((2, n), np.float32)
    for at in np.arange(0.25, SECONDS - 1.0, 1.75):
        i = int(at * SR)
        x[:, i:i + hit.shape[1]] += hit[:, :n - i]
    return x


def render_frames(rows, names, dry):
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "frames").mkdir(parents=True)
    dry.T.astype("<f4").tofile(WORK / "input.f32")
    with open(WORK / "params.txt", "w") as f:
        for vals, cam in rows:
            f.write(" ".join(f"{x:.6f}" for x in list(vals) + list(cam)) + "\n")
    os.environ["SE_UI_DEMO"] = os.fspath(WORK)
    for k in ("SE_UI_SNAPSHOT", "SE_UI_T", "SE_UI_TIME", "SE_UI_VIEW"):
        os.environ.pop(k, None)
    p = pedalboard.load_plugin(os.fspath(VST3))
    close = threading.Event()
    png_dir = WORK / "png"
    png_dir.mkdir()

    def convert():
        done = 0
        t0 = time.time()
        while done < len(rows) and time.time() - t0 < 1800:
            ppm = WORK / "frames" / f"f{done:05d}.ppm"
            nxt = WORK / "frames" / f"f{done + 1:05d}.ppm"
            if ppm.exists() and (nxt.exists() or (WORK / "done").exists()):
                Image.open(ppm).save(png_dir / f"f{done:05d}.png")
                ppm.unlink()
                done += 1
                if done % 48 == 0:
                    print(f"  frame {done}/{len(rows)}")
            else:
                time.sleep(0.05)
        close.set()

    threading.Thread(target=convert, daemon=True).start()
    p.show_editor(close)
    del os.environ["SE_UI_DEMO"]
    return png_dir


def render_audio(rows, names, labels):
    p = pedalboard.load_plugin(os.fspath(VST3))
    dry = dry_input()
    out = np.zeros_like(dry)
    for k, (vals, _) in enumerate(rows):
        for n, x in zip(names, vals):
            if n == "map":
                p.map = labels[int(x)]
            elif n == "view":
                p.view = p.parameters["view"].valid_values[int(x)]
            elif n == "division":
                p.division = p.parameters["division"].valid_values[int(x)]
            elif n == "sync":
                p.sync = bool(x)
            else:
                setattr(p, n, x)
        out[:, k * BLOCK:(k + 1) * BLOCK] = p.process(dry[:, k * BLOCK:(k + 1) * BLOCK], SR, reset=(k == 0))
    g = 0.891 / max(np.abs(out).max(), 1e-9)
    wav = WORK / "wet.wav"
    sf.write(wav, (out * g).T, SR, subtype="PCM_16")
    return wav


def main():
    probe = pedalboard.load_plugin(os.fspath(VST3))
    names = list(probe.parameters.keys())
    labels = probe.parameters["map"].valid_values
    del probe
    rows = script(names, labels)
    dry = dry_input()
    if "--mux-only" in sys.argv:
        png_dir = WORK / "png"
    else:
        png_dir = render_frames(rows, names, dry)
    n_png = len(list(png_dir.glob("*.png")))
    print("frames", n_png)
    wav = render_audio(rows, names, labels)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.fspath(png_dir / "f%05d.png"),
                    "-i", os.fspath(wav), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", os.fspath(OUT)], check=True)
    print("wrote", OUT.relative_to(PLUGIN), f"{OUT.stat().st_size // 1024} KiB")


if __name__ == "__main__":
    main()
