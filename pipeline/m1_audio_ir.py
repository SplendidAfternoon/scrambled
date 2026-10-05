"""Render retrocausal audio from the already-measured otoc-echo trajectories (uploaded as `ir`)."""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

IR_DIR = ROOT / "renders" / "ir"
IR_DIR.mkdir(parents=True, exist_ok=True)

RENDER = {"min_level": 0.02, "decay": 1.0, "master_ms": 6400, "negative_mode": "invert",
          "mix": 0.6, "include_tap_map": True, "emit": "audio"}


def ir_asset(name):
    rec = json.loads((ROOT / "probes" / f"otoc_{name}.json").read_text(encoding="utf-8"))
    p = IR_DIR / f"{name}.json"
    p.write_text(json.dumps({"result": rec["response"]["result"]}), encoding="utf-8")
    return moth.upload(p)


def render(name, stem):
    rec = moth.run("retrocausal-echo-v1", RENDER, {"audio": stem, "ir": ir_asset(name)}, timeout=900)
    paths = moth.fetch_outputs(rec, ROOT / "renders" / "retro")
    return name, rec["job_id"], rec["seconds"], {k: str(v) for k, v in paths.items()}


if __name__ == "__main__":
    stem = moth.upload(ROOT / "media" / "prep" / "stem_20s.wav")
    names = sys.argv[1:] or ["scrambling", "control_clifford"]
    with ThreadPoolExecutor(2) as pool:
        for fut in [pool.submit(render, n, stem) for n in names]:
            try:
                print("ok", *fut.result(), flush=True)
            except Exception as e:
                print("ERR", str(e)[:1500], flush=True)
