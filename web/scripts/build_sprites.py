"""Egg sprites: classical crops of the two egg photos, then a quantum round trip through tessa-image-v1 on Atlas.

Run from the repo root:  .venv\\Scripts\\python web\\scripts\\build_sprites.py
Writes web/scripts/sprite_src/*.png (classical inputs), web/public/sprites/*.png (Atlas outputs)
and web/public/data/sprites.json (job ids + params).
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

SRC = ROOT / "web" / "scripts" / "sprite_src"
OUT = ROOT / "web" / "public" / "sprites"
DATA = ROOT / "web" / "public" / "data"
SIZE = 128


def masked(img, box, shape="ellipse", pad=6):
    crop = img.crop(box)
    w = round(SIZE * crop.width / crop.height) if shape == "ellipse" else SIZE
    im = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    x0 = (SIZE - w) // 2
    im.paste(crop.resize((w, SIZE), Image.LANCZOS).convert("RGBA"), (x0, 0))
    m = Image.new("L", (SIZE, SIZE), 0)
    d = ImageDraw.Draw(m)
    if shape == "ellipse":
        d.ellipse([x0 + pad, pad, x0 + w - pad, SIZE - pad], fill=255)
    else:  # blob: soft round splat
        d.ellipse([pad, pad + 8, SIZE - pad, SIZE - pad - 4], fill=255)
    im.putalpha(m.filter(ImageFilter.GaussianBlur(1.2)))
    return im


def sources():
    SRC.mkdir(parents=True, exist_ok=True)
    a = Image.open(ROOT / "media" / "prep" / "A_sq.jpg").convert("RGB")
    b = Image.open(ROOT / "media" / "prep" / "B_sq.jpg").convert("RGB")
    srcs = {
        "egg_whole": masked(a, (382, 513, 587, 768), pad=1),  # front egg, tight ellipse
        "egg_scrambled": masked(b, (300, 380, 560, 640), shape="blob"),
    }
    paths = {}
    for k, im in srcs.items():
        p = SRC / f"{k}.png"
        im.save(p)
        paths[k] = p
    return paths


# Tessa first. distortion > 0 is rejected on emulators (distortion_without_hardware), so its "cooking" states come
# from fewer shots (sampling noise) and an IBM-calibrated noisy emulator. If Tessa is unavailable, the same sprite is
# made with blur-v1 (qubit-rotation blur; the sprite's alpha acts as the mask) at increasing strength.
SPRITES = [
    # name, source, tessa params, blur-v1 fallback params
    ("egg_fresh", "egg_whole", {"shots": 4096}, {"strength": 0.05, "reach": 0}),
    ("egg_crack", "egg_whole", {"shots": 256}, {"strength": 0.25, "reach": 0}),
    ("egg_cook", "egg_whole", {"shots": 48}, {"strength": 0.45, "reach": 0}),
    ("egg_burnt", "egg_whole", {"machine": "fake_torino", "shots": 1024}, {"strength": 0.6, "reach": 0.2}),
    ("egg_scrambled", "egg_scrambled", {"shots": 4096}, {"strength": 0.08, "reach": 0}),
    ("egg_scrambled_hot", "egg_scrambled", {"shots": 64}, {"strength": 0.35, "reach": 0.3}),
]
TESSA_UP = {"ok": None}  # None = unknown, False after the first Tessa failure


def make(name, src, tessa, blur, asset):
    errors = []
    if TESSA_UP["ok"] is not False:
        params = {"machine": "aer", "shots": 4096, **tessa}
        try:
            rec = moth.run("tessa-image-v1", params, {"image": asset}, timeout=600)
            TESSA_UP["ok"] = True
            return rec, params, errors
        except moth.MothError as e:
            TESSA_UP["ok"] = TESSA_UP["ok"] or False
            errors.append(f"tessa-image-v1: {str(e)[:200]}")
    rec = moth.run("blur-v1", blur, {"image": asset}, timeout=600)
    return rec, blur, errors


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srcs = sources()
    assets = {k: moth.upload(p) for k, p in srcs.items()}
    meta = {}
    with ThreadPoolExecutor(2) as pool:
        futs = {pool.submit(make, name, src, tessa, blur, assets[src]): (name, src) for name, src, tessa, blur in SPRITES}
        for fut in as_completed(futs):
            name, src = futs[fut]
            try:
                rec, params, tried = fut.result()
                paths = moth.fetch_outputs(rec, ROOT / "web" / "scripts" / "tessa_raw")
                Image.open(paths["result"]).convert("RGBA").save(OUT / f"{name}.png")
                meta[name] = {"job_id": rec["job_id"], "engine_id": rec["engine_id"], "source": f"{src}.png",
                              "params": params, "seconds": rec["seconds"], "fallback_from": tried or None}
                print("ok", name, rec["engine_id"], rec["seconds"], flush=True)
            except Exception as e:
                meta[name] = {"error": str(e)[:400], "source": f"{src}.png", "params": {}}
                print("ERR", name, str(e)[:300], flush=True)
    (DATA / "sprites.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
