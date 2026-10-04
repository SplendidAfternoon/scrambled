"""Submit every otoc-echo-v1 run used by the piece and the size study; raw records -> measurements/raw/.

All runs: aer emulator, exact expectation values, chain lattice, Z kick at the centre, depth 32.
Re-running is free: moth.run returns the content-addressed cache hit.
"""
import json
import math
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

RAW = ROOT / "measurements" / "raw"

BASE = {
    "depth": 32, "n_sites": 12, "min_tap_level": 0, "include_taps": True,
    "machine": "aer", "exact": True, "disorder": 0, "lattice": "chain", "kick": "Z",
    "theta_x": 0.3 * math.pi, "theta_z": 0, "theta_zz": 0.35 * math.pi, "via": "direct",
}
# The two original probes used these exact float spellings; keep them so the cache hits.
BASE["theta_x"] = 0.9424777960769379
BASE["theta_zz"] = 1.0995574287564276

RUNS = {
    "scrambling_n12": BASE,
    "control_clifford_n12": {**BASE, "theta_zz": math.pi},
    "lowx_n12": {**BASE, "theta_x": 0.1 * math.pi},
    "scrambling_n8": {**BASE, "n_sites": 8},
    "scrambling_n10": {**BASE, "n_sites": 10},
    "scrambling_n16": {**BASE, "n_sites": 16},
    "scrambling_n24": {**BASE, "n_sites": 24},
    "lowx_n8": {**BASE, "theta_x": 0.1 * math.pi, "n_sites": 8},
    "control_clifford_n8": {**BASE, "theta_zz": math.pi, "n_sites": 8},
    "lowx_n10": {**BASE, "theta_x": 0.1 * math.pi, "n_sites": 10},
}


def one(name, params, timeout, retries=4):
    t0 = time.time()
    for attempt in range(retries + 1):
        try:
            rec = moth.run("otoc-echo-v1", params, timeout=timeout)
            break
        except moth.MothError as e:
            if '"retryable": true' not in str(e) or attempt == retries:
                raise
            with (RAW / "failed_jobs.log").open("a", encoding="utf-8") as f:
                f.write(f"{name} attempt {attempt}: {str(e)[:400]}\n")
            time.sleep(60 * (attempt + 1))
    rec.setdefault("name", name)
    (RAW / f"{name}.json").write_text(json.dumps(rec, indent=2), encoding="utf-8")
    return name, rec["job_id"], rec["seconds"], round(time.time() - t0, 1)


def main(names, workers=2):
    RAW.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(workers) as pool:
        futs = {pool.submit(one, n, RUNS[n], 7200 if "n24" in n else 1800): n for n in names}
        for f in as_completed(futs):
            try:
                print("ok", *f.result(), flush=True)
            except Exception as e:  # keep the others going
                print("ERR", futs[f], str(e)[:800], flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or list(RUNS))
