"""The OTOC map F(site, t): measure it on Atlas (otoc-echo-v1), parse it, or simulate it classically.

Physics (as run by otoc-echo-v1 on a 1-D chain): every qubit starts in |+>. One Floquet step is
``U = Rx(theta_x)^{(x)n} . exp(-i theta_zz/2 sum Z_i Z_{i+1})``. For each echo depth t the circuit applies U^t, a
Pauli kick V on the kick site, then U^-t, and measures <X_i> + i<Y_i> on every site, divided by the same quantity
without the kick. That ratio is the out-of-time-order correlator

    F(i, t) = <psi| W_i(0)^dagger V(t)^dagger W_i(0) V(t) |psi> / reference,   V(t) = U^-t V U^t

F = 1 means site i cannot tell the kick happened; F = -1 means it sees a clean flip; |F| < 1 means the kick's
information has been scrambled into many-body correlations. The region where F != 1 is the light cone.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

ENGINE = "otoc-echo-v1"


def parse_angle(text):
    """'0.3pi' / '0.3*pi' / 'pi' / '0.94' -> radians."""
    s = str(text).strip().lower().replace(" ", "")
    m = re.fullmatch(r"([0-9.eE+-]*)\*?(pi|π)", s)
    try:
        if m:
            return (float(m.group(1)) if m.group(1) not in ("", "+") else 1.0) * math.pi
        return float(s)
    except ValueError:
        raise ValueError(f"not an angle: {text!r} (use radians or e.g. 0.3pi)") from None


def _num(x):
    """Ints for exact zeros, so params hash identically to the original measurement scripts."""
    return 0 if x == 0 else float(x)


@dataclass(frozen=True)
class OTOCParams:
    n_sites: int = 12
    depth: int = 32
    theta_x: float = 0.3 * math.pi
    theta_zz: float = 0.35 * math.pi
    theta_z: float = 0.0
    kick: str = "Z"
    kick_site: int | None = None
    disorder: float = 0.0
    machine: str = "aer"

    @property
    def resolved_kick_site(self):
        return self.n_sites // 2 if self.kick_site is None else self.kick_site

    @property
    def is_clifford(self):
        return math.isclose(self.theta_zz % math.pi, 0, abs_tol=1e-12) or math.isclose(
            self.theta_zz % math.pi, math.pi, abs_tol=1e-12)

    def engine_params(self):
        p = {"depth": self.depth, "n_sites": self.n_sites, "min_tap_level": 0, "include_taps": True,
             "machine": self.machine, "exact": True, "disorder": _num(self.disorder), "lattice": "chain",
             "kick": self.kick, "theta_x": float(self.theta_x), "theta_z": _num(self.theta_z),
             "theta_zz": float(self.theta_zz), "via": "direct"}
        if self.kick_site is not None:
            p["kick_site"] = self.kick_site
        return p


@dataclass
class OTOCMap:
    F: np.ndarray                  # complex, shape (n_sites, depth); column t-1 is echo depth t
    kick_site: int
    source: str                    # atlas | classical
    params: dict = field(default_factory=dict)
    job_id: str | None = None
    backend: str | None = None

    @property
    def n_sites(self):
        return self.F.shape[0]

    @property
    def depth(self):
        return self.F.shape[1]

    @property
    def label(self):
        if self.source == "atlas":
            return f"measured on Moth Atlas, otoc-echo-v1 ({self.backend or 'aer'} emulator)" \
                if (self.backend or "aer") == "aer" else f"measured on Moth Atlas, otoc-echo-v1 ({self.backend})"
        return "classical numpy simulation (no quantum hardware or emulator)"

    def summary(self):
        absF = np.abs(self.F)
        off = np.delete(absF, self.kick_site, axis=0).mean(axis=0)
        tail = off[len(off) // 2:]
        return {"source": self.source, "label": self.label, "job_id": self.job_id, "shape": list(self.F.shape),
                "kick_site": self.kick_site, "light_cone_arrival_t": [int(a) if a else None for a in arrival_steps(self.F)],
                "late_mean_absF_offkick": round(float(tail.mean()), 3), "params": self.params}

    def save(self, path):
        d = {"format": "scrambled.otoc-map/1", "source": self.source, "job_id": self.job_id, "backend": self.backend,
             "kick_site": self.kick_site, "params": self.params, "F_re": self.F.real.tolist(),
             "F_im": self.F.imag.tolist()}
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(d, indent=1), encoding="utf-8")
        return Path(path)


def parse_record(rec):
    """otoc-echo-v1 job record (as cached by AtlasClient.run) -> OTOCMap."""
    out = rec["response"]["result"]["output"]
    s = out["data"]["series"]
    F = np.array(s["F_re"], dtype=float) + 1j * np.array(s["F_im"], dtype=float)
    ex = out["extras"]
    return OTOCMap(F=F, kick_site=int(ex["kick_site"]), source="atlas", params=ex.get("params") or rec.get("params", {}),
                   job_id=rec.get("job_id"), backend=(out.get("provenance") or {}).get("backend"))


def load(path):
    """Load a saved OTOCMap JSON, or a raw otoc-echo-v1 job record."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    if d.get("format", "").startswith("scrambled.otoc-map"):
        F = np.array(d["F_re"]) + 1j * np.array(d["F_im"])
        return OTOCMap(F=F, kick_site=d["kick_site"], source=d["source"], params=d.get("params") or {},
                       job_id=d.get("job_id"), backend=d.get("backend"))
    return parse_record(d)


def light_cone(F, tol=1e-6):
    """Boolean (site, t): has the kick ever been visible at this site by depth t?"""
    return np.maximum.accumulate(np.abs(F - 1) > tol, axis=1)


def arrival_steps(F, tol=1e-6):
    cone = light_cone(F, tol)
    return [int(np.argmax(row)) + 1 if row.any() else None for row in cone]


# -- classical reference simulation ---------------------------------------------------------------------------
_X = np.array([[0, 1], [1, 0]], complex)
_Y = np.array([[0, -1j], [1j, 0]], complex)
_Z = np.array([[1, 0], [0, -1]], complex)


def simulate(params: OTOCParams):
    """Exact statevector OTOC. Verified to 1e-12 against otoc-echo-v1 (aer, exact) for the conventions it supports."""
    if params.theta_z != 0:
        raise NotImplementedError("classical mode: theta_z ordering is not verified against Atlas; use --mode atlas")
    if params.disorder != 0:
        raise NotImplementedError("classical mode: disorder model 'additive-v1' is not reproduced; use --mode atlas")
    n = params.n_sites
    if n > 18:
        raise NotImplementedError("classical mode is limited to 18 sites; use --mode atlas")
    k = params.resolved_kick_site
    if not 0 <= k < n:
        raise ValueError(f"kick_site {k} outside chain of {n}")
    shape = [2] * n
    z = 1 - 2 * ((np.arange(2 ** n)[:, None] >> (n - 1 - np.arange(n))) & 1)
    zz = (z[:, :-1] * z[:, 1:]).sum(axis=1)
    fwd_phase = np.exp(-0.5j * params.theta_zz * zz)
    c, s = math.cos(params.theta_x / 2), math.sin(params.theta_x / 2)
    rx_f = np.array([[c, -1j * s], [-1j * s, c]])
    rx_b = rx_f.conj().T
    kick = {"X": _X, "Y": _Y, "Z": _Z}[params.kick]

    def one_q(psi, U, q):
        t = np.tensordot(U, psi.reshape(shape), axes=([1], [q]))
        return np.moveaxis(t, 0, q).reshape(-1)

    def step(psi, forward):
        if forward:
            psi = psi * fwd_phase
            for q in range(n):
                psi = one_q(psi, rx_f, q)
        else:
            for q in range(n):
                psi = one_q(psi, rx_b, q)
            psi = psi * fwd_phase.conj()
        return psi

    psi = np.full(2 ** n, 2 ** (-n / 2), complex)
    F = np.empty((n, params.depth), complex)
    for t in range(1, params.depth + 1):
        psi = step(psi, True)
        phi = one_q(psi, kick, k)
        for _ in range(t):
            phi = step(phi, False)
        for i in range(n):
            F[i, t - 1] = np.vdot(phi, one_q(phi, _X, i)).real + 1j * np.vdot(phi, one_q(phi, _Y, i)).real
    return OTOCMap(F=F, kick_site=k, source="classical", params={**params.engine_params(), "kick_site": k})


def measure(params: OTOCParams, mode="atlas", client=None, timeout=600):
    """Get F(site, t) for these params: Atlas job (cached), cache-only replay, or classical simulation."""
    if mode == "classical":
        return simulate(params)
    if client is None:
        from scrambled.client import AtlasClient
        client = AtlasClient(mode=mode)
    rec = client.run(ENGINE, params.engine_params(), timeout=timeout)
    return parse_record(rec)
