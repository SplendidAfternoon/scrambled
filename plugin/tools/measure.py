"""Measure the Scrambled Echo tap maps on Moth Atlas (otoc-echo-v1, aer exact emulator).

Every run goes through moth.run (content-addressed cache in ../cache/), so re-running is free and
MODE=replay rebuilds everything offline. Writes plugin/tools/measured.json (name -> job record path).

    .venv\\Scripts\\python plugin\\tools\\measure.py
"""
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

PI = math.pi
BASE = {"depth": 32, "n_sites": 12, "min_tap_level": 0, "include_taps": True, "machine": "aer",
        "exact": True, "disorder": 0, "lattice": "chain", "kick": "Z",
        "theta_x": 0.3 * PI, "theta_z": 0, "theta_zz": 0.35 * PI, "via": "direct"}

# name -> param overrides. "scrambling" and "control_clifford" reproduce the probes/ runs exactly (cache hits).
RUNS = {
    "scrambling": {},
    "control_clifford": {"theta_zz": PI},
    "low_theta_x": {"theta_x": 0.1 * PI},
    "sparse": {"theta_zz": 0.25 * PI},
    "phase": {"theta_z": 0.25 * PI},
    "disorder": {"disorder": 0.6, "seed": 7},
    "wide14_d16": {"n_sites": 14, "depth": 16},
    # Off-centre kicks break the chain's mirror symmetry, so the light cone moves across the stereo field.
    "kick_left": {"kick_site": 2},
    "edge_sparse": {"kick_site": 0, "theta_zz": 0.25 * PI},
}
# Wider chains hit the engine's own timeout on 2026-10-04 (n_sites/depth -> job):
# 16/32 0994f20d-5c09-4479-8a78-fd0d4ac009f1, 24/32 e4585c82-c100-4669-9301-d46d928296ee,
# 14/32 482f1c75-0e31-46c5-89dd-47c38d9290d1, 16/16 4c12d40b-fbb9-4144-b284-e139d30a31a2.


def check_schema():
    live = moth.get("/engines/otoc-echo-v1")["params_schema"]["properties"]
    for name, over in RUNS.items():
        unknown = set({**BASE, **over}) - set(live)
        if unknown:
            raise SystemExit(f"{name}: params not in live schema: {unknown}")


def one(item):
    name, over = item
    params = {**BASE, **over}
    try:
        rec = moth.run("otoc-echo-v1", params, timeout=900)
    except Exception as e:  # never block the whole set on one job
        return name, None, str(e)[:300]
    path = moth.CACHE / "otoc-echo-v1" / f"{moth.cache_key('otoc-echo-v1', params)}.json"
    return name, {"path": str(path.relative_to(ROOT)), "job_id": rec["job_id"], "params": params}, None


if __name__ == "__main__":
    if moth.MODE != "replay":
        check_schema()
    out = {}
    with ThreadPoolExecutor(4) as ex:
        for name, info, err in ex.map(one, RUNS.items()):
            print(name, info["job_id"] if info else f"FAILED: {err}")
            if info:
                out[name] = info
    (Path(__file__).with_name("measured.json")).write_text(json.dumps(out, indent=2), encoding="utf-8")
