"""F(site, t) -> what each vertical strip of the media does at a given moment.

The media is cut into one vertical strip per qubit (site). Media time runs along the echo depth t = 1..T. At each
moment a strip reads its own echo value F = F(site, t):

* |F| (echo *memory*): 1 = the strip still remembers its original state -> sharp; lower = blurred.
* sign of Re F (polarity): negative = the strip sees the kick as a flip -> it is shown inverted (vertical flip).
* scramble progress: the time integral of (1 - |F|). Information that leaked away does not come back on its own in a
  large system, so this accumulates; past a threshold the strip starts morphing toward the scrambled target.

The Clifford control (theta_zz = pi) has F = +-1 exactly, so it produces no blur, no morph, and a flip only on the
kicked strip, which is the "no scrambling" baseline.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

THRESHOLD = 0.3
GAIN = 1.6


@dataclass(frozen=True)
class StripState:
    blur: float     # 0 = sharp, 1 = maximally blurred
    morph: float    # 0 = original content, 1 = fully at the scramble target
    flipped: bool   # polarity of the echo: Re F < 0


def F_at(F, t):
    """F at continuous echo depth t (1-based), clamped to [1, T].

    F only exists at integer depths. Between them |F| is interpolated linearly and the phase is taken from the
    nearer depth, so a clean +1 -> -1 flip stays at |F| = 1 instead of passing through 0 (which would fake a loss of
    memory that was never measured).
    """
    T = F.shape[1]
    t = float(np.clip(t, 1, T))
    if T == 1:
        return F[:, 0]
    i = min(int(t) - 1, T - 2)
    f = t - (i + 1)
    mag = np.abs(F[:, i]) * (1 - f) + np.abs(F[:, i + 1]) * f
    near = F[:, i] if f < 0.5 else F[:, i + 1]
    return mag * np.exp(1j * np.angle(near))


def scramble_progress(F, t, gain=GAIN, samples=513):
    """Per-site cumulative scramble in [0, 1]: gain * (1/(T-1)) * integral_1^t (1 - |F(u)|) du."""
    T = F.shape[1]
    if T == 1:
        return np.zeros(F.shape[0])
    t = float(np.clip(t, 1, T))
    u = np.linspace(1, t, max(2, int(samples * (t - 1) / (T - 1)) + 2))
    loss = np.stack([1 - np.abs(F_at(F, x)) for x in u], axis=1)
    integral = np.trapezoid(loss, u, axis=1) if hasattr(np, "trapezoid") else np.trapz(loss, u, axis=1)
    return np.clip(gain * integral / (T - 1), 0, 1)


def strip_states(F, t, threshold=THRESHOLD, gain=GAIN):
    Ft = F_at(F, t)
    prog = scramble_progress(F, t, gain)
    out = []
    for s in range(F.shape[0]):
        mem = float(np.clip(abs(Ft[s]), 0, 1))
        blur = 0.0 if mem > 1 - 1e-9 else 1 - mem
        morph = 0.0 if prog[s] <= threshold else float((prog[s] - threshold) / (1 - threshold))
        out.append(StripState(blur=blur, morph=morph, flipped=bool(Ft[s].real < 0)))
    return out


def strip_edges(width, n):
    return np.linspace(0, width, n + 1).round().astype(int)
