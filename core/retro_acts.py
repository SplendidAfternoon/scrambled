"""Render each act's echo on Atlas: the act's cooking-stem segment through retrocausal-echo-v1, with ir = that act's
measured otoc-echo-v1 trajectory (n = 12). Wet only (mix 1.0); core/arrange.py does the mixing.

The three acts are submitted in parallel. Each submitted job id is written to cache/pending/retrocausal-echo-v1/
before polling, so a re-run resumes the same job instead of paying again. Completed jobs land in the normal
content-addressed cache (moth.cache_key) and outputs in renders/core/retro/acts/. Status: measurements/retro/acts.json.
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))
import moth  # noqa: E402
from arrange import SR, stem  # noqa: E402
from timeline import SEGMENTS, STEM_WINDOW, STEP_S, XFADE_S  # noqa: E402

ENGINE = "retrocausal-echo-v1"
DEPTH = 32
PARAMS = {"min_level": 0.02, "decay": 1.0, "master_ms": round(DEPTH * STEP_S * 1000), "negative_mode": "invert",
          "mix": 1.0, "include_tap_map": True, "emit": "audio"}
ACTS = ROOT / "renders" / "core" / "retro" / "acts"
PENDING = moth.CACHE / "pending" / ENGINE
STATUS = ROOT / "measurements" / "retro" / "acts.json"
TIMEOUT_S = 20 * 60


def inputs(name, run, t0, t1):
    """Write the act's dry segment (exactly what arrange.py convolves) and its IR envelope; upload both."""
    ACTS.mkdir(parents=True, exist_ok=True)
    w0, _ = STEM_WINDOW[name]
    dry = stem()[int(w0 * SR):int(w0 * SR) + int((t1 - t0 + XFADE_S) * SR)]
    clip = ACTS / f"dry_{name}.wav"
    sf.write(clip, dry / max(1.0, np.abs(dry).max()), SR, subtype="PCM_24")
    raw = json.loads((ROOT / "measurements" / "raw" / f"{run}.json").read_text(encoding="utf-8"))
    ir = ACTS / f"ir_{run}.json"
    ir.write_text(json.dumps({"result": raw["response"]["result"]}), encoding="utf-8")
    return {"audio": moth.upload(clip), "ir": moth.upload(ir)}, raw["job_id"]


def run_act(name, run, t0, t1):
    files, ir_job = inputs(name, run, t0, t1)
    key = moth.cache_key(ENGINE, PARAMS, files)
    done = moth.CACHE / ENGINE / f"{key}.json"
    out = {"act": name, "run": run, "ir_job_id": ir_job, "cache_key": key}
    if done.exists():
        rec = json.loads(done.read_text(encoding="utf-8"))
    else:
        pend = PENDING / f"{key}.json"
        if pend.exists():
            job_id = json.loads(pend.read_text(encoding="utf-8"))["job_id"]
        else:
            job_id = moth._req("POST", f"/engines/{ENGINE}/process",
                               json={"params": PARAMS, "input_files": files})["job_id"]
            PENDING.mkdir(parents=True, exist_ok=True)
            pend.write_text(json.dumps({"job_id": job_id, "act": name, "params": PARAMS, "input_files": files,
                                        "submitted": time.strftime("%Y-%m-%dT%H:%M:%S")}, indent=2),
                            encoding="utf-8")
        out["job_id"] = job_id
        t_start, st = time.time(), {}
        while time.time() - t_start < TIMEOUT_S:
            st = moth.get(f"/jobs/{job_id}/status")
            if st.get("status") in ("completed", "failed", "cancelled"):
                break
            time.sleep(20)
        out.update(status=st.get("status"), progress=(st.get("progress") or {}).get("detail"),
                   error=st.get("error"))
        if st.get("status") != "completed":
            if st.get("status") in ("failed", "cancelled"):
                pend.unlink(missing_ok=True)       # a failed job cannot be resumed; next run resubmits
            return out
        rec = {"engine_id": ENGINE, "params": PARAMS, "input_files": files, "job_id": job_id,
               "seconds": round(time.time() - t_start, 1), "response": moth.get(f"/jobs/{job_id}/result")}
        done.parent.mkdir(parents=True, exist_ok=True)
        done.write_text(json.dumps(rec, indent=2), encoding="utf-8")
        pend.unlink(missing_ok=True)
    paths = moth.fetch_outputs(rec, ACTS)
    out.update(status="completed", job_id=rec["job_id"], seconds=rec["seconds"],
               outputs={k: str(v.relative_to(ROOT)) for k, v in paths.items()})
    return out


def main():
    acts = [(n, r, t0, t1) for n, t0, t1, r in SEGMENTS if r]
    with ThreadPoolExecutor(len(acts)) as ex:
        res = list(ex.map(lambda a: run_act(*a), acts))
    prev = json.loads(STATUS.read_text(encoding="utf-8")) if STATUS.exists() else {}
    log = {"engine": ENGINE, "params": PARAMS, "checked": time.strftime("%Y-%m-%dT%H:%M:%S"),
           "acts": {r["act"]: r for r in res}, "history": prev.get("history", [])}
    log["history"].append({r["act"]: (r.get("job_id"), r.get("status")) for r in res})
    STATUS.write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(json.dumps(log["acts"], indent=2))


if __name__ == "__main__":
    main()
