"""The butterfly front compiled into a circuit: qdrive-api-v1.

QDrive builds a circuit from target expectation values instead of gates. For each echo step t = 0..7 the
target is a 12-qubit state whose single-qubit <Z_j> equals the measured Re F(j, t) (n=12 OTOC,
otoc-echo-v1 8df5cfa2). Inside the light cone F has dropped, outside it is still +1, so each circuit's
magnetisation profile is a frozen snapshot of the scrambling front; the 8 circuits step through the cone.
Single-qubit targets only need a product state (QDrive returns rz/ry/rz per qubit, no entangling gates):
this encodes the measured numbers, it does not re-run the echo dynamics. The achieved <Z_j> is computed
classically from the returned QASM and compared with the target.

Run:  .venv\\Scripts\\python extra\\qdrive\\run.py      (MODE=replay rebuilds from cache)
"""
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import fmap  # noqa: E402
import moth  # noqa: E402

HERE = Path(__file__).parent
T_STARS = range(8)  # the light cone crosses the 12-site chain in ~6 steps


def circuit_Z(qasm, n):
    """<Z_j> of the returned circuit on |0...0>, computed classically: each qubit gets rz.ry.rz only."""
    ry = {}
    for a, q in re.findall(r"ry\(([-0-9.eE+]+)\) q\[(\d+)\]", qasm):
        ry[int(q)] = ry.get(int(q), 0.0) + float(a)
    assert "cx" not in qasm and "cz" not in qasm, "entangling gates: per-qubit formula no longer valid"
    return np.cos([ry.get(j, 0.0) for j in range(n)])


def one(z):
    targets = [{"qubits": [j], "expvals": {"Z": float(z[j])}} for j in range(len(z))]
    params = {"n_qubits": len(z), "targets": targets, "tomography": 1, "shots": 4096, "seed": 12,
              "update_method": "spectral", "machine": "aer", "sample": False}
    rec = moth.run("qdrive-api-v1", params, timeout=600)
    path = moth.fetch_outputs(rec, HERE / "out")["circuit"]
    return rec, path


def main():
    F, _ = fmap.load_F(json.loads((ROOT / "probes" / "otoc_scrambling.json").read_text(encoding="utf-8")))
    n = F.shape[0]
    steps, target, got = [], [], []
    for t in T_STARS:
        z = np.round(F.real[:, t], 3)
        rec, path = one(z)
        zc = circuit_Z(path.read_text(encoding="utf-8"), n)
        steps.append({"t": t, "job_id": rec["job_id"], "seconds": rec["seconds"],
                      "circuit": path.relative_to(ROOT).as_posix(), "target_Z": z.tolist(),
                      "circuit_Z": np.round(zc, 4).tolist(), "max_abs_err": round(float(np.abs(zc - z).max()), 4),
                      "inline_result": rec["response"].get("result")})
        target.append(z)
        got.append(zc)
        print(t, rec["job_id"][:8], "max |dZ|", steps[-1]["max_abs_err"], flush=True)
    (HERE / "results.json").write_text(json.dumps({"engine_id": "qdrive-api-v1",
                                                   "source": "probes/otoc_scrambling.json Re F(site, t)",
                                                   "steps": steps}, indent=2), encoding="utf-8")
    figure(np.array(target).T, np.array(got).T)


def figure(T, G):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 3, figsize=(11, 4), dpi=150, facecolor="#141414")
    for ax, M, title, cm, lim in [(axes[0], T, "target: measured Re F(site, t)", "RdBu", (-1, 1)),
                                  (axes[1], G, "<Z> of the QDrive circuits", "RdBu", (-1, 1)),
                                  (axes[2], G - T, "difference", "RdBu", (-0.1, 0.1))]:
        im = ax.imshow(M, cmap=cm, vmin=lim[0], vmax=lim[1], aspect="auto", interpolation="nearest")
        ax.set_title(title, color="#eee", fontsize=9)
        ax.set_xlabel("echo step t (one circuit each)", color="#bbb", fontsize=8)
        ax.set_ylabel("site / qubit", color="#bbb", fontsize=8)
        ax.tick_params(colors="#bbb", labelsize=7)
        cb = fig.colorbar(im, ax=ax, fraction=0.046)
        cb.ax.tick_params(colors="#bbb", labelsize=7)
    fig.suptitle("The light cone, compiled: qdrive-api-v1 builds one 12-qubit circuit per echo step whose "
                 "<Z_j> is the measured front", color="#fff", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(HERE / "front_circuits.png", facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
