"""Can error correction unscramble the egg?  tamagotchi-v1 (Steane [[7,1,3]] code, 0 credits).

Toy mapping (stated in the card): the Steane block's 7 physical qubits stand in for the 7 chain sites around
the kick (sites 3-9 of the measured n=12 OTOC, kick at 6). At echo step t each site's disturbance is
d(j,t) = (1 - Re F(j,t)) / 2 = C(j,t)/4, the squared commutator as a fraction of its maximum. Its mean over
the 7 sites is used as the idle depolarizing rate p_idle for one noisy syndrome-extraction round, and the
engine reports how often the logical qubit survives after correction.

A reference sweep over p shows where the code helps (low, sparse error rates) and where it cannot.
Bare-qubit comparison 2p/3 is a classical formula, not an engine result.

Run:  .venv\\Scripts\\python extra\\tamagotchi\\run.py      (MODE=replay rebuilds from cache)
"""
import json
import sys
from concurrent.futures import ThreadPoolExecutor
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
BLOCK = slice(3, 10)
SWEEP = [0.001, 0.003, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5]
SHOTS, SEED = 4096, 7


def params(p):
    return {"code": "steane", "n_logical": 1, "actions": [["I", 0], ["SE", 0]], "shots": SHOTS, "seed": SEED,
            "noise": {"p_idle": round(float(p), 4), "p_1q": 0, "p_gate": 0, "p_meas": 0}}


def run(p):
    rec = moth.run("tamagotchi-v1", params(p), timeout=600)
    o = rec["response"]["result"]["output"]
    return {"p_idle": params(p)["noise"]["p_idle"], "job_id": rec["job_id"], "success_rate": o["success_rate"],
            "syndromes_detected": o["syndromes_detected"], "corrections_applied": o["corrections_applied"]}


def main():
    F, _ = fmap.load_F(json.loads((ROOT / "probes" / "otoc_scrambling.json").read_text(encoding="utf-8")))
    d = ((1 - F.real) / 2)[BLOCK].mean(axis=0)
    with ThreadPoolExecutor(3) as pool:
        sweep = list(pool.map(run, SWEEP))
        echo = list(pool.map(run, d))
    for t, e in enumerate(echo):
        e["t"] = t
        e["disturbance"] = round(float(d[t]), 4)
    out = {"engine_id": "tamagotchi-v1", "source": "probes/otoc_scrambling.json (otoc-echo-v1 8df5cfa2)",
           "block_sites": [3, 9], "shots": SHOTS, "seed": SEED, "actions": [["I", 0], ["SE", 0]],
           "sweep": sweep, "echo": echo}
    (HERE / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    card(sweep, echo)
    best = max(echo, key=lambda e: e["success_rate"])
    print(f"sweep: {[(s['p_idle'], s['success_rate']) for s in sweep]}")
    print(f"echo: min p={min(e['p_idle'] for e in echo)} best survival {best['success_rate']:.3f} at t={best['t']}")


def card(sweep, echo):
    fig, (a, b) = plt.subplots(1, 2, figsize=(12, 4.8), dpi=150, facecolor="#141414")
    for ax in (a, b):
        ax.set_facecolor("#141414")
        ax.tick_params(colors="#ddd")
        for s in ax.spines.values():
            s.set_color("#666")
    p = np.array([s["p_idle"] for s in sweep])
    a.plot(p, [1 - s["success_rate"] for s in sweep], "o-", color="#f2c14e", label="Steane logical error (tamagotchi-v1)")
    a.plot(p, 2 * p / 3, "--", color="#aaa", label="unencoded qubit, one step: 2p/3 (classical reference)")
    lo, hi = min(e["p_idle"] for e in echo), max(e["p_idle"] for e in echo)
    a.axvspan(lo, hi, color="#e4572e", alpha=0.25, label="measured egg disturbance, all echo steps")
    a.set_xscale("log")
    a.set_yscale("symlog", linthresh=1e-3)
    a.set_ylim(0, 1)
    a.set_xlabel("idle depolarizing rate p per physical qubit", color="#ddd")
    a.set_ylabel("logical failure after one corrected round", color="#ddd")
    a.legend(facecolor="#222", labelcolor="#ddd", fontsize=8, loc="upper left")
    a.set_title("Error correction works for sparse errors", color="#fff")
    t = [e["t"] for e in echo]
    b.plot(t, [e["success_rate"] for e in echo], "o-", color="#f2c14e", label="logical survival (tamagotchi-v1)")
    b.plot(t, [1 - e["disturbance"] for e in echo], "-", color="#e4572e", alpha=0.7, label="1 - mean disturbance of the 7 sites")
    b.axhline(0.5, color="#888", ls=":", lw=1)
    b.text(31, 0.47, "0.5 = coin flip", color="#888", fontsize=7.5, ha="right", va="top")
    b.set_ylim(0, 1.02)
    b.set_xlabel("echo step t (measured OTOC, n=12)", color="#ddd")
    b.set_ylabel("probability", color="#ddd")
    b.legend(facecolor="#222", labelcolor="#ddd", fontsize=8, loc="lower right")
    b.set_title("...but the scrambled egg is far past what it can fix", color="#fff")
    fig.suptitle("Can error correction unscramble the egg?  Steane [[7,1,3]] code on Moth Atlas (aer stabilizer sim)",
                 color="#fff", fontsize=11)
    fig.text(0.5, 0.005, "Toy mapping: the 7 code qubits stand for chain sites 3-9 around the kick; each site's "
             "disturbance (1 - Re F)/2 becomes an idle depolarizing rate.\nScrambling itself is unitary and is undone "
             "by the time-reversed echo; a local error-correcting code is not the tool that undoes it.",
             ha="center", color="#aaa", fontsize=7.5)
    fig.tight_layout(rect=(0, 0.06, 1, 0.94))
    fig.savefig(HERE / "qec_card.png", facecolor=fig.get_facecolor())


if __name__ == "__main__":
    main()
