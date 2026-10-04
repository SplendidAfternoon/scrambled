"""Measure the otoc-echo-v1 grid on Atlas (cached via moth.run) and export compact JSON for the web app.

Run from the repo root:  .venv\\Scripts\\python web\\scripts\\build_data.py
Writes web/public/data/grid.json and web/public/data/featured.json.
"""
import json
import math
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import moth  # noqa: E402

OUT = ROOT / "web" / "public" / "data"
PI = math.pi

N_SITES = [8, 12]
THETA_X = [0.1, 0.2, 0.3, 0.4, 0.5]           # units of pi
THETA_ZZ = [0.15, 0.25, 0.35, 0.5, 0.75, 1.0]  # units of pi; 1.0 = Clifford
DEPTH = 32


def params(n, tx, tzz):
    return {"n_sites": n, "depth": DEPTH, "theta_x": tx * PI, "theta_zz": tzz * PI,
            "machine": "aer", "exact": True, "include_taps": False}


HEALTH = {"ok": 0, "fail": 0}


def measure(p, attempts=3):
    """moth.run with retries: the platform answers engine_timeout (retryable) under load.
    Fails fast once the first few jobs have all failed, so an outage doesn't cost an hour of timeouts."""
    for i in range(attempts):
        if HEALTH["ok"] == 0 and HEALTH["fail"] >= 4 and moth.cache_key("otoc-echo-v1", p) not in CACHED:
            raise moth.MothError("skipped: otoc-echo-v1 is failing every job right now")
        try:
            rec = moth.run("otoc-echo-v1", p, timeout=600)
            HEALTH["ok"] += 1
            return rec
        except moth.MothError as e:
            HEALTH["fail"] += 1
            if i == attempts - 1 or "retryable\": true" not in str(e).replace("'", '"'):
                raise


CACHED = {f.stem for f in (ROOT / "cache" / "otoc-echo-v1").glob("*.json")}


def compact(rec, label=None):
    out = rec["response"]["result"]["output"]
    s = out["data"]["series"]
    ex = out["extras"]
    p = rec["params"]
    fim = s["F_im"]
    is_real = all(abs(v) < 1e-9 for row in fim for v in row)
    r4 = lambda rows: [[round(float(v), 4) for v in row] for row in rows]  # noqa: E731
    return {
        "label": label,
        "job_id": rec["job_id"],
        "engine_id": rec["engine_id"],
        "params": {"n_sites": p["n_sites"], "depth": p["depth"],
                   "theta_x_pi": round(p["theta_x"] / PI, 4), "theta_zz_pi": round(p["theta_zz"] / PI, 4)},
        "kick_site": ex["kick_site"],
        "backend": out["provenance"]["backend"],
        "library_version": out["provenance"].get("library_version"),
        "F_re": r4(s["F_re"]),
        "F_im": None if is_real else r4(fim),
        "light_cone": ex["light_cone"],
        "summary": {k: ex["summary"][k] for k in ("live", "inverted", "regular", "erased")},
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(n, tx, tzz) for n in N_SITES for tx in THETA_X for tzz in THETA_ZZ]
    runs, errors = [], []
    with ThreadPoolExecutor(2) as pool:
        futs = {pool.submit(measure, params(*j)): j for j in jobs}
        for fut in as_completed(futs):
            j = futs[fut]
            try:
                runs.append(compact(fut.result()))
                print("ok", j, flush=True)
            except Exception as e:  # keep going; a missing cell falls back to nearest neighbour in the app
                errors.append({"cell": j, "error": str(e)[:160]})
                print("ERR", j, str(e)[:200], flush=True)
    # Earlier measured runs from the shared cache (same engine, clean Floquet, depth 32) fill grid gaps.
    have = {(r["params"]["n_sites"], r["params"]["theta_x_pi"], r["params"]["theta_zz_pi"]) for r in runs}
    for f in sorted((ROOT / "cache" / "otoc-echo-v1").glob("*.json")):
        rec = json.loads(f.read_text(encoding="utf-8"))
        p = rec["params"]
        if (p.get("depth") != DEPTH or p.get("disorder", 0) or p.get("lattice", "chain") != "chain" or p.get("theta_z", 0)
                or p.get("kick", "Z") != "Z" or p.get("machine", "aer") != "aer" or p.get("kick_site") is not None):
            continue
        c = compact(rec)
        k = (c["params"]["n_sites"], c["params"]["theta_x_pi"], c["params"]["theta_zz_pi"])
        if k not in have:
            have.add(k)
            runs.append(c)
    runs.sort(key=lambda r: (r["params"]["n_sites"], r["params"]["theta_x_pi"], r["params"]["theta_zz_pi"]))
    grid = {"engine_id": "otoc-echo-v1", "axes": {"n_sites": N_SITES, "theta_x_pi": THETA_X, "theta_zz_pi": THETA_ZZ},
            "depth": DEPTH, "runs": runs, "errors": errors}
    (OUT / "grid.json").write_text(json.dumps(grid, separators=(",", ":")), encoding="utf-8")

    featured = []
    for name, label in (("otoc_scrambling", "Scrambling (theta_x 0.3pi, theta_zz 0.35pi)"),
                        ("otoc_control_clifford", "Clifford control (theta_zz = pi)")):
        rec = json.loads((ROOT / "probes" / f"{name}.json").read_text(encoding="utf-8"))
        featured.append(compact(rec, label))
    (OUT / "featured.json").write_text(json.dumps(featured, separators=(",", ":")), encoding="utf-8")
    print(f"grid: {len(runs)} runs, {len(errors)} errors")


if __name__ == "__main__":
    main()
