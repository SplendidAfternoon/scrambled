"""Challenge 01 hero: photo A (whole eggs) through blur-v1, strength set by the measured scrambling.

strength = 1 - late-time mean |F| of the measured n=12 OTOC (otoc-echo-v1 8df5cfa2): how much of the
echo is lost once the kick has scrambled. reach is swept: 0 = local blur, 1 = any pixel can reach any
other, i.e. the image analogue of the kick spreading over the whole chain.

Run:  .venv\\Scripts\\python hero\\ladder.py          (MODE=replay to rebuild from cache only)
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import fmap  # noqa: E402
import moth  # noqa: E402

HERE = ROOT / "hero"
OUT = HERE / "ladder"
ENGINE = "blur-v1"


def measured_strength():
    rec = json.loads((ROOT / "probes" / "otoc_scrambling.json").read_text(encoding="utf-8"))
    F, _ = fmap.load_F(rec)
    late = float(np.abs(F)[:, 16:].mean())
    return late, round(1.0 - late, 2)


def png_input():
    dst = HERE / "input_A_sq.png"
    if not dst.exists():
        Image.open(ROOT / "media" / "prep" / "A_sq.jpg").convert("RGB").save(dst, optimize=True)
    return dst


def ladder(s):
    rungs = [(s, r, st) for st in ("rx", "ry") for r in (0.25, 0.5, 0.8, 1.0)]
    rungs += [(0.6, 0.8, "rx"), (0.9, 0.8, "rx")]
    rungs += [(s, 0.15, "rx"), (s, 0.35, "rx")]  # second pass: only reach <= 0.25 still reads as eggs
    return rungs


def main():
    late, s = measured_strength()
    print(f"late mean |F| (t>=16) = {late:.3f} -> strength {s}")
    inp = png_input()
    asset = moth.upload(inp)
    jobs = ladder(s)
    results = []
    with ThreadPoolExecutor(4) as pool:
        futs = {pool.submit(moth.run, ENGINE, {"strength": st, "reach": r, "style": sty}, {"image": asset},
                            timeout=900): (st, r, sty) for st, r, sty in jobs}
        for fut in as_completed(futs):
            st, r, sty = futs[fut]
            try:
                rec = fut.result()
                p = moth.fetch_outputs(rec, OUT)["result"]
                results.append({"strength": st, "reach": r, "style": sty, "job_id": rec["job_id"],
                                "seconds": rec["seconds"], "file": p.relative_to(ROOT).as_posix()})
                print("ok", st, r, sty, rec["job_id"][:8], flush=True)
            except Exception as e:
                results.append({"strength": st, "reach": r, "style": sty, "error": str(e)[:500]})
                print("ERR", st, r, sty, str(e)[:300], flush=True)
    results.sort(key=lambda d: (d["style"], d["strength"] != s, d["reach"], d["strength"]))
    (OUT / "index.json").write_text(json.dumps({"late_mean_absF": round(late, 4), "strength_from_F": s,
                                                "input": inp.relative_to(ROOT).as_posix(), "input_asset": asset,
                                                "rungs": results}, indent=2), encoding="utf-8")
    contact(results, inp)


def contact(results, inp, tile=320, pad=8, cols=4):
    items = [("input (photo A)", inp)] + [
        (f"s={d['strength']} reach={d['reach']} {d['style']}  {d['job_id'][:8]}", ROOT / d["file"])
        for d in results if "file" in d]
    rows = -(-len(items) // cols)
    W, H = cols * (tile + pad) + pad, rows * (tile + 30 + pad) + pad
    sheet = Image.new("RGB", (W, H), (18, 18, 18))
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("arial.ttf", 15)
    except OSError:
        font = ImageFont.load_default()
    for i, (label, path) in enumerate(items):
        x, y = pad + (i % cols) * (tile + pad), pad + (i // cols) * (tile + 30 + pad)
        sheet.paste(Image.open(path).convert("RGB").resize((tile, tile), Image.LANCZOS), (x, y))
        draw.text((x + 2, y + tile + 6), label, fill=(230, 230, 230), font=font)
    sheet.save(HERE / "ladder_contact.jpg", quality=90)


if __name__ == "__main__":
    main()
