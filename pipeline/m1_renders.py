"""M1: prepare media, upload, and render the Tier-0 quantum assets (blur levels, telablur levels, retrocausal audio)."""
import json
import math
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

MEDIA = ROOT / "media"
PREP = MEDIA / "prep"
OUT = ROOT / "renders"
PREP.mkdir(parents=True, exist_ok=True)

OTOC = {"depth": 32, "n_sites": 12, "machine": "aer", "exact": True, "disorder": 0,
        "theta_x": 0.9424777960769379, "theta_z": 0, "theta_zz": 1.0995574287564276}


def prep_photo(src, dst):
    if not dst.exists():
        im = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        im.thumbnail((1024, 1024))
        im.save(dst, quality=92)
    return dst


def prep_audio(src, dst, start, dur):
    if not dst.exists():
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(start), "-t", str(dur), "-i", str(src),
                        "-ac", "1", "-ar", "48000", str(dst)], check=True)
    return dst


def main(stage):
    a = moth.upload(prep_photo(MEDIA / "photo_A_whole.jpg", PREP / "A.jpg"))
    b = moth.upload(prep_photo(MEDIA / "photo_B_scrambled.jpg", PREP / "B.jpg"))
    stem = moth.upload(prep_audio(MEDIA / "stem_full.wav", PREP / "stem_20s.wav", 0, 20))
    print("assets:", a, b, stem)

    jobs = []
    if stage in ("all", "images"):
        for s in (0.2, 0.4, 0.6, 0.8, 1.0):
            jobs.append(("blur", s, "blur-v1", {"strength": s, "reach": s}, {"image": a}))
        for s in (0.125, 0.25, 0.375, 0.5, 0.625, 0.75, 0.875, 1.0):
            jobs.append(("telablur", s, "telablur-v1", {"strength": s}, {"image1": a, "image2": b}))
    if stage in ("all", "audio"):
        audio = {"min_level": 0.02, "decay": 1.0, "master_ms": 6400, "negative_mode": "invert",
                 "mix": 0.6, "include_tap_map": True, "emit": "audio"}
        jobs.append(("retro", "scrambling", "retrocausal-echo-v1", {**OTOC, **audio}, {"audio": stem}))
        jobs.append(("retro", "control", "retrocausal-echo-v1",
                     {**OTOC, "theta_zz": math.pi, **audio}, {"audio": stem}))

    results = {}
    with ThreadPoolExecutor(4) as pool:
        futs = {pool.submit(moth.run, eid, p, f): (kind, lvl) for kind, lvl, eid, p, f in jobs}
        for fut in as_completed(futs):
            kind, lvl = futs[fut]
            try:
                rec = fut.result()
                paths = moth.fetch_outputs(rec, OUT / kind)
                results[f"{kind}:{lvl}"] = {"job_id": rec["job_id"], "seconds": rec["seconds"],
                                            "files": {k: str(v.relative_to(ROOT)) for k, v in paths.items()}}
                print(f"ok  {kind} {lvl}  {rec['seconds']}s  {list(paths)}")
            except Exception as e:
                results[f"{kind}:{lvl}"] = {"error": str(e)[:1500]}
                print(f"ERR {kind} {lvl}: {str(e)[:600]}")
    (OUT / f"m1_{stage}.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "all")
