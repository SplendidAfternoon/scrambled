"""The measured scrambling map, sent through a quantum image encoding: qpixl-v1.

The 12 x 32 grid |F(site, t)| of the n=12 OTOC (otoc-echo-v1 8df5cfa2, values in [0, 1]) is flattened
row-major (site-major) and encoded with Interwoven QPIXL, then decoded from measurement. Two runs:
  aer        - noiseless emulator, finite shots only
  fake_fez   - emulator calibrated to IBM Fez's noise (156 qubits; fake_torino's 378-value capacity is too small)
The decoded grids are rendered as heatmaps and used as the texture band of extra/poster/.

Run:  .venv\\Scripts\\python extra\\qpixl\\run.py      (MODE=replay rebuilds from cache)
"""
import json
import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import fmap  # noqa: E402
import moth  # noqa: E402

HERE = Path(__file__).parent
MACHINES = ["aer", "fake_fez"]  # fake_torino rejected 384 values (capacity 378), job 0a3945c1


def grid():
    F, _ = fmap.load_F(json.loads((ROOT / "probes" / "otoc_scrambling.json").read_text(encoding="utf-8")))
    return np.round(np.abs(F), 4)


def params(values, machine):
    return {"values": values, "machine": machine, "mode": "emu", "shots": 4096, "discretize": 0,
            "dynamic_range": "none", "allow_high_shots": False}


def decoded(result, n):
    """Find the reconstructed array in the engine's inline JSON (field name undocumented)."""
    cands = []

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, path + [k])
        elif isinstance(x, list) and x and all(isinstance(v, (int, float)) for v in x):
            cands.append((path, x))
        elif isinstance(x, list) and x and all(isinstance(v, list) for v in x):
            flat = [u for v in x for u in (v if isinstance(v, list) else [v])]
            if flat and all(isinstance(u, (int, float)) for u in flat):
                cands.append((path, flat))
    walk(result, [])
    return cands


def main(machines=MACHINES):
    A = grid()
    values = A.flatten().tolist()
    prev = HERE / "results.json"
    runs = json.loads(prev.read_text(encoding="utf-8"))["runs"] if prev.exists() else {}
    for m in machines:
        try:
            rec = moth.run("qpixl-v1", params(values, m), timeout=900)
        except moth.MothError as e:
            runs[m] = {"error": str(e)[:600]}
            print("ERR", m, str(e)[:300])
            continue
        res = rec["response"]["result"]
        (HERE / f"raw_{m}.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
        cands = decoded(res, A.size)
        pick = next(((p, v) for p, v in cands if len(v) >= A.size and "input" not in "/".join(map(str, p)).lower()
                     and not np.allclose(v[:A.size], values)), None)
        if pick is None:
            runs[m] = {"job_id": rec["job_id"], "error": "no decoded array found",
                       "candidates": [("/".join(map(str, p)), len(v)) for p, v in cands]}
            print("no decoded array", m, runs[m]["candidates"])
            continue
        D = np.array(pick[1][:A.size], dtype=float).reshape(A.shape)
        runs[m] = {"job_id": rec["job_id"], "seconds": rec["seconds"], "field": "/".join(map(str, pick[0])),
                   "rmse": round(float(np.sqrt(((D - A) ** 2).mean())), 4),
                   "corr": round(float(np.corrcoef(D.ravel(), A.ravel())[0, 1]), 4)}
        np.save(HERE / f"decoded_{m}.npy", D)
        print(m, rec["job_id"][:8], runs[m])
    (HERE / "results.json").write_text(json.dumps({"engine_id": "qpixl-v1", "shape": list(A.shape),
                                                   "source": "probes/otoc_scrambling.json |F|, row = site",
                                                   "runs": runs}, indent=2), encoding="utf-8")
    render(A, runs)


def render(A, runs):
    panels = [("measured |F| (otoc-echo-v1)", A)]
    for m, r in runs.items():
        if (HERE / f"decoded_{m}.npy").exists() and "rmse" in r:
            panels.append((f"qpixl-v1 {m}  {r['job_id'][:8]}  rmse {r['rmse']}", np.load(HERE / f"decoded_{m}.npy")))
    fig, axes = plt.subplots(len(panels), 1, figsize=(9, 2.6 * len(panels)), dpi=160, facecolor="#141414")
    for ax, (title, M) in zip(np.atleast_1d(axes), panels):
        ax.imshow(M, cmap="magma", vmin=0, vmax=1, aspect="auto", interpolation="nearest")
        ax.set_title(title, color="#eee", fontsize=9)
        ax.set_xlabel("echo step t", color="#bbb", fontsize=8)
        ax.set_ylabel("site", color="#bbb", fontsize=8)
        ax.tick_params(colors="#bbb", labelsize=7)
    fig.tight_layout()
    fig.savefig(HERE / "qpixl_compare.png", facecolor=fig.get_facecolor())
    for m in runs:
        p = HERE / f"decoded_{m}.npy"
        if p.exists():
            plt.imsave(HERE / f"texture_{m}.png", np.repeat(np.repeat(np.load(p), 32, 0), 32, 1),
                       cmap="magma", vmin=0, vmax=1)
    plt.imsave(HERE / "texture_measured.png", np.repeat(np.repeat(A, 32, 0), 32, 1), cmap="magma", vmin=0, vmax=1)


if __name__ == "__main__":
    main(sys.argv[1:] or MACHINES)
