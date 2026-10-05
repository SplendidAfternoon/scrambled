"""Piece v4 image ladders, re-run on lossless input.

Source: the original 3072x4080 photos, square crop (0, 800, 3072, 3872) as in pipeline/m1b_images.py, exported as PNG.
1024 px PNGs go to the engines (their pixel budget is 1024); 1080 px PNGs are the compositor's A/B endpoints.
blur-v1  : A, strength = reach = s (the "blurR" ladder the piece used).
telablur-v1 : A -> B at strength s, direction full or vertical.
Outputs: renders/core/ladder/<key>.<ext>, index in renders/core/ladder/index.json. Jobs run 4 at a time.
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

OUT = ROOT / "renders" / "core" / "ladder"
PHOTOS = {"A": "media/photo_A_whole.jpg", "B": "media/photo_B_scrambled.jpg"}
CROP = (0, 800, 3072, 3872)


def prep():
    OUT.mkdir(parents=True, exist_ok=True)
    paths = {}
    for k, src in PHOTOS.items():
        sq = ImageOps.exif_transpose(Image.open(ROOT / src)).convert("RGB").crop(CROP)
        for size in (1024, 1080):
            p = OUT / f"{k}_{size}.png"
            if not p.exists():
                sq.resize((size, size), Image.LANCZOS).save(p)
            paths[f"{k}_{size}"] = p
    return paths


def jobs(spec):
    """spec: list of (key, engine, params). Returns {key: {file, job_id, params, engine}}."""
    paths = prep()
    a, b = moth.upload(paths["A_1024"]), moth.upload(paths["B_1024"])
    idx_path = OUT / "index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8")) if idx_path.exists() else {}

    def one(item):
        key, engine, params = item
        files = {"image": a} if engine == "blur-v1" else {"image1": a, "image2": b}
        for attempt in range(3):
            try:
                rec = moth.run(engine, params, files, poll=3, max_poll=10, timeout=900)
                break
            except moth.MothError as e:
                if '"retryable": true' not in str(e) or attempt == 2:
                    return key, {"error": str(e)[:300]}
        p = moth.fetch_outputs(rec, OUT)
        res = p.get("result") or next(iter(p.values()))
        return key, {"file": str(res.relative_to(ROOT)), "job_id": rec["job_id"], "params": params, "engine": engine}

    with ThreadPoolExecutor(4) as ex:
        for key, r in ex.map(one, spec):
            idx[key] = r
            print(key, r.get("job_id", r.get("error")), flush=True)
    idx_path.write_text(json.dumps(idx, indent=2), encoding="utf-8")
    return idx


PROBE = [("tela_full:0.95", "telablur-v1", {"strength": 0.95}),
         ("tela_vert:0.95", "telablur-v1", {"strength": 0.95, "direction": "vertical"}),
         ("tela_vert:0.8", "telablur-v1", {"strength": 0.8, "direction": "vertical"}),
         ("blurR:0.2", "blur-v1", {"strength": 0.2, "reach": 0.2})]

if __name__ == "__main__":
    spec = PROBE
    if "--spec" in sys.argv:
        spec = [tuple(x) for x in json.loads(Path(sys.argv[sys.argv.index("--spec") + 1]).read_text())]
    jobs(spec)
