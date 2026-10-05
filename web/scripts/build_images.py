"""Ship the Atlas blur-v1 / telablur-v1 image ladders (already rendered by pipeline/m1b_images.py) as static web assets.

Run from the repo root:  .venv\\Scripts\\python web\\scripts\\build_images.py
Writes web/public/img/ladder/*.jpg and web/public/data/ladder.json.
"""
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "img" / "ladder"
DATA = ROOT / "web" / "public" / "data"
SIZE = 512

# Ladders: "memory" fades whole -> blurred (blur-v1, reach 0 on photo A),
# then "scrambled" morphs whole -> scrambled (telablur-v1 between photo A and photo B).
BLUR = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]
TELA = [0.02, 0.05, 0.1, 0.15, 0.5, 0.85, 0.9, 0.95, 0.98]


def save(src, name):
    Image.open(ROOT / src).convert("RGB").resize((SIZE, SIZE), Image.LANCZOS).save(OUT / name, quality=82)
    return f"img/ladder/{name}"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    idx = json.loads((ROOT / "renders" / "v2" / "index.json").read_text(encoding="utf-8"))
    blur = [{"file": save("media/prep/A_sq.jpg", "A.jpg"), "engine_id": None, "strength": 0, "job_id": None}]
    for s in BLUR:
        e = idx[f"blurR:{s}"]
        blur.append({"file": save(e["file"], f"blur_{s}.jpg"), "engine_id": "blur-v1", "strength": s, "job_id": e["job_id"]})
    tela = []
    for s in TELA:
        e = idx[f"telablur:{s}"]
        tela.append({"file": save(e["file"], f"tela_{s}.jpg"), "engine_id": "telablur-v1", "strength": s, "job_id": e["job_id"]})
    b = save("media/prep/B_sq.jpg", "B.jpg")
    (DATA / "ladder.json").write_text(json.dumps({"size": SIZE, "blur": blur, "tela": tela, "A": "img/ladder/A.jpg", "B": b},
                                                 indent=1), encoding="utf-8")
    print(len(blur), len(tela))


if __name__ == "__main__":
    main()
