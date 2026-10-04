"""Compose the SCRAMBLED piece: per-qubit strips driven by the measured F(site, t), plus audio, via ffmpeg."""
import json
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from audio_local import render as render_audio
from fmap import load_F

ROOT = Path(__file__).parent
OUT = ROOT / "out"
FPS = 24
SIZE = 1024
ACT1 = 14.0   # control (Clifford, no scrambling)
ACT2 = 44.0   # scrambling run, 32 echo steps

idx = json.loads((ROOT / "renders" / "v2" / "index.json").read_text(encoding="utf-8"))


def img(path):
    return np.asarray(Image.open(ROOT / path).convert("RGB").resize((SIZE, SIZE)), dtype=np.float32)


A = img("media/prep/A_sq.jpg")
BLUR = [A] + [img(idx[f"blurR:{s}"]["file"]) for s in (0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4)]
TELA = [img(idx[f"telablur:{s}"]["file"]) for s in (0.02, 0.05, 0.1, 0.15, 0.5, 0.85, 0.9, 0.95, 0.98)]


def ladder(stack, x):
    """Crossfade along an image ladder; x in [0, 1]."""
    x = float(np.clip(x, 0, 1)) * (len(stack) - 1)
    i = min(int(x), len(stack) - 2)
    f = x - i
    return stack[i] * (1 - f) + stack[i + 1] * f


def F_at(F, t):
    """Linear interpolation of F along echo steps; t is 1-based and continuous."""
    t = np.clip(t, 1, F.shape[1])
    i = min(int(t) - 1, F.shape[1] - 2)
    f = t - (i + 1)
    return F[:, i] * (1 - f) + F[:, i + 1] * f


def strip_frame(F, t, cum, control=False):
    n = F.shape[0]
    edges = np.linspace(0, SIZE, n + 1).astype(int)
    frame = np.empty_like(A)
    Ft = F_at(F, t)
    for s in range(n):
        mem = abs(Ft[s])
        if cum[s] < 0.35:
            tile = ladder(BLUR, 1 - mem)
        else:
            tile = ladder(TELA, (cum[s] - 0.35) / 0.65)
        if control and Ft[s].real < 0:
            tile = TELA[-1]
        elif Ft[s].real < 0:
            tile = tile[::-1]
        frame[:, edges[s]:edges[s + 1]] = tile[:, edges[s]:edges[s + 1]]
    return frame


def heatmap_overlay(F, t, w=300, h=112):
    from matplotlib import colormaps
    rgb = colormaps["RdBu"](np.clip((F.real + 1) / 2, 0, 1))[..., :3]
    im = Image.fromarray((rgb * 255).astype(np.uint8)).resize((w, h), Image.NEAREST)
    d = ImageDraw.Draw(im)
    x = int((t - 1) / (F.shape[1] - 1) * (w - 1))
    d.line([(x, 0), (x, h)], fill=(255, 255, 255), width=2)
    return im


def caption(frame, text, sub, F, t):
    im = Image.fromarray(frame.clip(0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("arial.ttf", 30)
        small = ImageFont.truetype("arial.ttf", 20)
    except OSError:
        font = small = ImageFont.load_default()
    d.rectangle([0, SIZE - 70, SIZE, SIZE], fill=(0, 0, 0))
    d.text((20, SIZE - 64), text, fill="white", font=font)
    d.text((20, SIZE - 30), sub, fill=(200, 200, 200), font=small)
    hm = heatmap_overlay(F, t)
    im.paste(hm, (SIZE - hm.width - 16, 16))
    d.text((SIZE - hm.width - 16, 16 + hm.height + 4), "measured echo F(qubit, t)", fill="white", font=small)
    return im


def main():
    OUT.mkdir(exist_ok=True)
    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    Fc, _ = load_F(json.loads((ROOT / "probes" / "otoc_control_clifford.json").read_text(encoding="utf-8")))
    Fs, _ = load_F(json.loads((ROOT / "probes" / "otoc_scrambling.json").read_text(encoding="utf-8")))

    n = 0
    for k in range(int(ACT1 * FPS)):
        t = 1 + 31 * k / (ACT1 * FPS)
        cum = np.zeros(Fc.shape[0])
        fr = strip_frame(Fc, t, cum, control=True)
        caption(fr, "I. Control: a circuit that cannot scramble",
                "otoc-echo-v1, theta_zz = pi (Clifford). Only the nudged qubit flips.", Fc, t).save(frames_dir / f"{n:05d}.jpg", quality=90)
        n += 1
    cum = np.zeros(Fs.shape[0])
    total = int(ACT2 * FPS)
    for k in range(total):
        t = 1 + 31 * k / total
        cum += (1 - np.abs(F_at(Fs, t))) / total * 1.45
        fr = strip_frame(Fs, t, np.clip(cum, 0, 1))
        caption(fr, "II. Scrambling: the nudge spreads through 12 qubits",
                f"otoc-echo-v1 on Moth Atlas (emulator), echo step t = {t:4.1f} / 32", Fs, t).save(frames_dir / f"{n:05d}.jpg", quality=90)
        n += 1

    stem = ROOT / "media" / "stem_full.wav"
    a1 = render_audio(stem, "control_clifford", OUT / "audio_control.wav")
    a2 = render_audio(stem, "scrambling", OUT / "audio_scrambling.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(a1), "-i", str(a2), "-filter_complex",
                    f"[0]atrim=0:{ACT1},afade=t=out:st={ACT1-1}:d=1[a];"
                    f"[1]atrim={ACT1}:{ACT1+ACT2},asetpts=PTS-STARTPTS,afade=t=in:d=1,afade=t=out:st={ACT2-2}:d=2[b];"
                    "[a][b]concat=n=2:v=0:a=1[o]", "-map", "[o]", str(OUT / "audio_piece.wav")], check=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(frames_dir / "%05d.jpg"),
                    "-i", str(OUT / "audio_piece.wav"), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(OUT / "scrambled_piece.mp4")], check=True)
    print("frames:", n, "->", OUT / "scrambled_piece.mp4")


if __name__ == "__main__":
    main()
