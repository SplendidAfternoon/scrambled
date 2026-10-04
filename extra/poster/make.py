"""SCRAMBLED poster, 1080 x 1350 (classical compositing of engine outputs).

Top: hero/hero.png (blur-v1, strength from the measured scrambling).
Band: the measured |F(site, t)| map after the qpixl-v1 round trip on the fake_fez noisy emulator,
next to the noiseless aer round trip, so the band itself is a quantum-encoded copy of the data.

Run:  .venv\\Scripts\\python extra\\poster\\make.py   (needs extra/qpixl/decoded_*.npy; no API calls)
"""
import json
from pathlib import Path

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
QP = ROOT / "extra" / "qpixl"
W, H = 1080, 1350


def font(size, bold=False):
    for name in (("arialbd.ttf" if bold else "arial.ttf"), "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def band(M, w, h):
    rgba = matplotlib.colormaps["magma"](np.clip(M, 0, 1))
    im = Image.fromarray((rgba[..., :3] * 255).astype(np.uint8))
    return im.resize((w, h), Image.NEAREST)


def main():
    runs = json.loads((QP / "results.json").read_text(encoding="utf-8"))["runs"]
    hero = json.loads((ROOT / "hero" / "params.json").read_text(encoding="utf-8"))
    canvas = Image.new("RGB", (W, H), (14, 14, 14))
    canvas.paste(Image.open(ROOT / "hero" / "hero.png").convert("RGB").resize((W, W), Image.LANCZOS), (0, 0))
    d = ImageDraw.Draw(canvas)
    d.text((36, 30), "SCRAMBLED", font=font(64, True), fill=(245, 240, 230))
    y0, bh, gap = W + 20, 72, 10
    for i, m in enumerate(["fake_fez", "aer"]):
        y = y0 + i * (bh + gap + 22)
        canvas.paste(band(np.load(QP / f"decoded_{m}.npy"), W - 72, bh), (36, y + 22))
        label = (f"|F(site, t)| after qpixl-v1 on {m}"
                 f"{' (IBM Fez noise model)' if m == 'fake_fez' else ' (noiseless)'}  ·  job {runs[m]['job_id'][:8]}")
        d.text((36, y), label, font=font(17), fill=(200, 200, 200))
    foot = (f"Photo: blur-v1 job {hero['job_id'][:8]}, strength {hero['params_full']['strength']} = 1 - late mean |F|, "
            f"reach {hero['params_full']['reach']}.  Data: otoc-echo-v1 job 8df5cfa2, 12 sites x 32 echo steps, aer emulator.")
    d.text((36, H - 34), foot, font=font(14), fill=(150, 150, 150))
    canvas.save(HERE / "scrambled_poster.png", optimize=True)
    canvas.save(HERE / "scrambled_poster.jpg", quality=92)
    print("poster", canvas.size)


if __name__ == "__main__":
    main()
