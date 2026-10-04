"""Export the chosen ladder rung as hero/hero.png + hero/params.json (full blur-v1 parameter set).

Run after hero/ladder.py. Reads the job from cache/ and the engine schema snapshot in hero/blur-v1_schema.json
(refreshed from GET /engines/blur-v1 unless MODE=replay).
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

HERE = ROOT / "hero"
CHOSEN = {"strength": 0.75, "reach": 0.25, "style": "rx"}


def schema():
    snap = HERE / "blur-v1_schema.json"
    if os.environ.get("MODE") != "replay":
        d = moth.get("/engines/blur-v1")
        keep = {k: d.get(k) for k in ("engine_id", "name", "version", "credits_per_run", "input_files",
                                       "output_files", "params_schema")}
        snap.write_text(json.dumps(keep, indent=2), encoding="utf-8")
    return json.loads(snap.read_text(encoding="utf-8"))


def main():
    idx = json.loads((HERE / "ladder" / "index.json").read_text(encoding="utf-8"))
    rung = next(r for r in idx["rungs"] if all(r.get(k) == v for k, v in CHOSEN.items()))
    asset = idx["input_asset"]
    rec = moth.run("blur-v1", CHOSEN, {"image": asset})  # cache hit
    assert rec["job_id"] == rung["job_id"]
    sch = schema()
    props = sch["params_schema"]["properties"]
    full = {k: v.get("default") for k, v in props.items()}
    full.update(rec["params"])
    unknown = set(rec["params"]) - set(props)
    assert not unknown, unknown

    src = ROOT / rung["file"]
    im = Image.open(src)
    assert im.format == "PNG" and im.size == (1024, 1024), (im.format, im.size)
    shutil.copyfile(src, HERE / "hero.png")
    out = {
        "challenge": "01 One image, one engine",
        "engine_id": "blur-v1",
        "engine_version": sch.get("version"),
        "job_id": rec["job_id"],
        "job_seconds": rec["seconds"],
        "credits": sch.get("credits_per_run"),
        "input_file": idx["input"],
        "input_asset_id": asset,
        "input_sha256": hashlib.sha256((ROOT / idx["input"]).read_bytes()).hexdigest(),
        "output_file": "hero/hero.png",
        "output_size": list(im.size),
        "output_note": "hero.png is the engine's result file byte-for-byte (PNG in, PNG out; 1024 is blur-v1's max size).",
        "params_sent": rec["params"],
        "params_full": full,
        "params_defaulted": sorted(set(full) - set(rec["params"])),
        "parameter_rationale": {
            "strength": f"1 - late-time mean |F| = 1 - {idx['late_mean_absF']:.3f} (n=12 OTOC, otoc-echo-v1 job 8df5cfa2, t>=16) -> {CHOSEN['strength']}",
            "reach": "0.25: picked from the ladder; the highest reach at which the eggs still read (0.35+ is unreadable)",
            "style": "rx: every ry rung at strength 0.75 came back black",
            "size": "default 1024 = input size = engine max, one pass over the whole frame",
        },
        "ladder": "hero/ladder/index.json, hero/ladder_contact.jpg",
    }
    (HERE / "params.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out["params_full"]), rec["job_id"])


if __name__ == "__main__":
    main()
