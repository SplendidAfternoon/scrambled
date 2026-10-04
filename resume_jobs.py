"""Attach to already-submitted jobs, wait for completion, and store them in the cache like moth.run would."""
import json
import sys
import time
from pathlib import Path

import moth

ROOT = Path(__file__).parent


def resume(job_id, engine_id, params, input_files, dest, poll=10):
    t0 = time.time()
    while True:
        st = moth.get(f"/jobs/{job_id}/status")
        if st["status"] == "completed":
            break
        if st["status"] in ("failed", "cancelled"):
            raise moth.MothError(f"{job_id} {st['status']}: {json.dumps(st)[:1500]}")
        print(f"{job_id[:8]} {st.get('progress')}", flush=True)
        time.sleep(poll)
    rec = {"engine_id": engine_id, "params": params, "input_files": input_files, "job_id": job_id,
           "seconds": None, "response": moth.get(f"/jobs/{job_id}/result")}
    key = moth.cache_key(engine_id, params, input_files)
    path = moth.CACHE / engine_id / f"{key}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rec, indent=2), encoding="utf-8")
    paths = moth.fetch_outputs(rec, dest)
    print("done", job_id[:8], round(time.time() - t0), "s", {k: str(v) for k, v in paths.items()}, flush=True)
    return rec


if __name__ == "__main__":
    from m1_audio_ir import RENDER, ir_asset
    stem = moth.upload(ROOT / "media" / "prep" / "stem_20s.wav")
    jobs = {"bc6516c5-c5c5-430d-a66a-fa2785a8ceb4": None, "c4eefe4b-402a-4da8-8f54-259114c39e3f": None}
    for jid in jobs:
        res = moth.get(f"/jobs/{jid}/status")
    from concurrent.futures import ThreadPoolExecutor
    mapping = {name: ir_asset(name) for name in ("scrambling", "control_clifford")}
    with ThreadPoolExecutor(2) as pool:
        futs = [pool.submit(resume, jid, "retrocausal-echo-v1", RENDER, None, ROOT / "renders" / "retro")
                for jid in jobs]
        for f in futs:
            try:
                f.result()
            except Exception as e:
                print("ERR", e, flush=True)
