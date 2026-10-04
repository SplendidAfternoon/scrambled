"""Load measured otoc-echo-v1 runs from measurements/raw/ and derive the summary numbers used everywhere."""
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "measurements" / "raw"
sys.path.insert(0, str(ROOT))
from fmap import load_F  # noqa: E402


def record(name):
    return json.loads((RAW / f"{name}.json").read_text(encoding="utf-8"))


CLASSICAL = ROOT / "measurements" / "classical"
ATLAS = "otoc-echo-v1 on Moth Atlas (aer emulator)"


def F_of(name, allow_classical=False):
    """Measured F[site, t] and extras (extras['source'] says where it came from).

    allow_classical=True falls back to the numpy statevector result when no engine record exists.
    """
    if (RAW / f"{name}.json").exists():
        F, ex = load_F(record(name))
        return F, {**ex, "source": ATLAS, "job_id": record(name)["job_id"]}
    if not allow_classical:
        raise FileNotFoundError(f"no engine record for {name}")
    rec = json.loads((CLASSICAL / f"{name}.json").read_text(encoding="utf-8"))
    F = np.array(rec["F_re"]) + 1j * np.array(rec["F_im"])
    return F, {"kick_site": rec["kick_site"], "source": "classical statevector", "job_id": None,
               "spec": rec["params"]}


def offkick(F, k):
    return np.delete(F, k, axis=0)


def scramble_strength(F, k):
    """1 - mean |F| over off-kick sites in the second half of the echo (0 = nothing lost, 1 = fully scrambled)."""
    late = np.abs(offkick(F, k))[:, F.shape[1] // 2:]
    return float(np.clip(1 - late.mean(), 0, 1))


def spread_fraction(F, k, tol=0.05):
    """Mean fraction of sites whose F has moved away from 1 (how far the perturbation reached)."""
    moved = np.abs(F - 1) > tol
    return float(moved.mean())


def arrival_times(F, k, tol=1e-3):
    """First echo step t at which F(site, t) departs from 1 (light-cone front), per site."""
    out = []
    for row in F:
        idx = np.nonzero(np.abs(row - 1) > tol)[0]
        out.append(int(idx[0]) + 1 if len(idx) else None)
    return out
