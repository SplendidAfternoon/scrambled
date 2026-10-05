"""M1b: square-cropped inputs and finer blur/telablur ladders in the readable ranges."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

PREP = ROOT / "media" / "prep"
OUT = ROOT / "renders" / "v2"

BLUR = [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5]
TELA = [0.02, 0.05, 0.1, 0.15, 0.85, 0.9, 0.95, 0.98]


def square(src, dst, y0=800):
    if not dst.exists():
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        w, h = im.size
        im = im.crop((0, y0, w, y0 + w)).resize((1024, 1024), Image.LANCZOS)
        im.save(dst, quality=92)
    return dst


def main():
    a = moth.upload(square(ROOT / "media" / "photo_A_whole.jpg", PREP / "A_sq.jpg"))
    b = moth.upload(square(ROOT / "media" / "photo_B_scrambled.jpg", PREP / "B_sq.jpg"))
    jobs = [("blur", s, "blur-v1", {"strength": s, "reach": 0}, {"image": a}) for s in BLUR]
    jobs += [("telablur", s, "telablur-v1", {"strength": s}, {"image1": a, "image2": b}) for s in TELA]
    results = {}
    with ThreadPoolExecutor(4) as pool:
        futs = {pool.submit(moth.run, eid, p, f, timeout=900): (k, lv) for k, lv, eid, p, f in jobs}
        for fut in as_completed(futs):
            k, lv = futs[fut]
            try:
                rec = fut.result()
                paths = moth.fetch_outputs(rec, OUT / k)
                results[f"{k}:{lv}"] = {"job_id": rec["job_id"], "file": str(paths["result"].relative_to(ROOT))}
                print("ok", k, lv, flush=True)
            except Exception as e:
                results[f"{k}:{lv}"] = {"error": str(e)[:800]}
                print("ERR", k, lv, str(e)[:300], flush=True)
    (OUT / "index.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
