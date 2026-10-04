"""Classical numpy statevector runs of the same Floquet OTOC (core/otoc_sim.py) -> measurements/classical/<name>.json.

Used (a) as the independent cross-check against otoc-echo-v1, and (b) to extend the size study where the
engine queue was unavailable. Every number produced here is labelled 'classical' downstream.
"""
import json
import math
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from measure import RUNS  # noqa: E402
from otoc_sim import otoc_F  # noqa: E402

OUT = ROOT / "measurements" / "classical"
EXTRA = {"scrambling_n20": {**RUNS["scrambling_n12"], "n_sites": 20},
         "lowx_n16": {**RUNS["lowx_n12"], "n_sites": 16}, "lowx_n24": {**RUNS["lowx_n12"], "n_sites": 24}}


def run(name):
    p = RUNS.get(name) or EXTRA[name]
    t0 = time.time()
    F = otoc_F(p["n_sites"], p["depth"], p["theta_x"], p["theta_zz"], p["theta_z"], order="zz_x")
    rec = {"name": name, "source": "classical numpy statevector (core/otoc_sim.py)", "params": p,
           "seconds": round(time.time() - t0, 2), "kick_site": p["n_sites"] // 2,
           "F_re": F.real.tolist(), "F_im": F.imag.tolist()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.json").write_text(json.dumps(rec), encoding="utf-8")
    return name, rec["seconds"]


if __name__ == "__main__":
    for n in sys.argv[1:] or [k for k in RUNS if "n24" not in k]:
        print(*run(n), flush=True)
