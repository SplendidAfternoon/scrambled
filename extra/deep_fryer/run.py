"""Photo B (scrambled eggs) through deep-fryer-v1, with gates taken from the measured circuit.

The scrambling run is a kicked Ising chain: RX(theta_x = 0.3 pi) kicks and RZZ(theta_zz = 0.35 pi) couplings.
deep-fryer applies a gate sequence to a qubit lattice per tile; we pass the run's single-qubit kick and a
z rotation at the coupling angle, [["rx", 0.3], ["rz", 0.35]], next to the engine default [["rx", 0.5]].
Whether the engine reads intensities in units of pi is not documented; the numbers are the run's angles/pi.

Run:  .venv\\Scripts\\python extra\\deep_fryer\\run.py      (MODE=replay rebuilds from cache)
"""
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

HERE = Path(__file__).parent
VARIANTS = {
    "measured_gates": {"gates": [["rx", 0.3], ["rz", 0.35]], "tile_size": 4},
    "engine_default": {"gates": [["rx", 0.5]], "tile_size": 4},
}


def png_input():
    dst = HERE / "input_B_sq.png"
    if not dst.exists():
        Image.open(ROOT / "media" / "prep" / "B_sq.jpg").convert("RGB").save(dst, optimize=True)
    return dst


def main():
    inp = png_input()
    asset = moth.upload(inp)
    runs = {}
    for name, p in VARIANTS.items():
        try:
            rec = moth.run("deep-fryer-v1", p, {"image": asset}, timeout=900)
            f = moth.fetch_outputs(rec, HERE / "out")["result"]
            runs[name] = {"params": p, "job_id": rec["job_id"], "seconds": rec["seconds"],
                          "file": f.relative_to(ROOT).as_posix()}
            print("ok", name, rec["job_id"][:8])
        except moth.MothError as e:
            runs[name] = {"params": p, "error": str(e)[:600]}
            print("ERR", name, str(e)[:300])
    (HERE / "results.json").write_text(json.dumps({"engine_id": "deep-fryer-v1", "input": inp.relative_to(ROOT).as_posix(),
                                                   "input_asset": asset, "runs": runs}, indent=2), encoding="utf-8")
    ok = [(n, Image.open(ROOT / r["file"]).convert("RGB")) for n, r in runs.items() if "file" in r]
    if ok:
        tiles = [("input", Image.open(inp).convert("RGB"))] + ok
        sheet = Image.new("RGB", (512 * len(tiles), 512), (20, 20, 20))
        for i, (_, im) in enumerate(tiles):
            sheet.paste(im.resize((512, 512), Image.LANCZOS), (512 * i, 0))
        sheet.save(HERE / "compare.jpg", quality=90)


if __name__ == "__main__":
    main()
