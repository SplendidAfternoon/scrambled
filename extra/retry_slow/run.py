"""One small retry each for the engines that never completed earlier: tessa-image-v1 and retrocausal-echo-v1.

tessa:        a 64x64 crop of photo A (whole eggs), machine aer, defaults otherwise.
retrocausal:  6-site chain, depth 8, no audio input -> the engine renders its own impulse response.
Each job gets a bounded local wait; a job still running is appended to extra/pending.json for extra/pending.py.

Run:  .venv\\Scripts\\python extra\\retry_slow\\run.py
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

HERE = Path(__file__).parent
PENDING = ROOT / "extra" / "pending.json"
WAIT_S = 600


def tiny_png():
    dst = HERE / "tessa_input_A_64.png"
    if not dst.exists():
        im = Image.open(ROOT / "media" / "prep" / "A_sq.jpg").convert("RGB")
        im.crop((192, 192, 832, 832)).resize((64, 64), Image.LANCZOS).save(dst)
    return dst


def attempt(engine, params, files, dirname):
    try:
        rec = moth.run(engine, params, files, timeout=WAIT_S)
        out = moth.fetch_outputs(rec, ROOT / "extra" / dirname)
        return {"engine_id": engine, "job_id": rec["job_id"], "status": "completed", "seconds": rec["seconds"],
                "files": {k: v.relative_to(ROOT).as_posix() for k, v in out.items()}, "params": params}
    except moth.MothError as e:
        m = re.search(r"job ([0-9a-f-]{36})", str(e))
        state = "local_timeout" if "timed out locally" in str(e) else "failed"
        return {"engine_id": engine, "job_id": m.group(1) if m else None, "status": state,
                "error": str(e)[:600], "params": params, "dir": dirname}


def main():
    a = moth.upload(tiny_png())
    tasks = [("tessa-image-v1", {"machine": "aer"}, {"image": a}, "tessa"),
             ("retrocausal-echo-v1", {"n_sites": 6, "depth": 8, "machine": "aer", "exact": True, "emit": "audio"},
              None, "retrocausal")]
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda t: attempt(*t), tasks))
    (HERE / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    pend = json.loads(PENDING.read_text(encoding="utf-8")) if PENDING.exists() else []
    known = {p["job_id"] for p in pend}
    for r in results:
        print(r["engine_id"], r["status"], (r["job_id"] or "")[:8], r.get("error", "")[:200])
        if r["status"] == "local_timeout" and r["job_id"] not in known:
            pend.append({"engine_id": r["engine_id"], "job_id": r["job_id"], "params": r["params"], "dir": r["dir"],
                         "status": "processing"})
    PENDING.write_text(json.dumps(pend, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
