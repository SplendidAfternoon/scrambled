"""Classical DSP: measured-tap impulse responses, convolution echo, reverb, limiter and loudness mastering."""
import numpy as np
import pyloudnorm as pyln
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import fftconvolve, resample_poly

SR = 48000


def tap_ir(F, step_s, sr=SR, decay=1.0, kick_site=None):
    """Stereo IR from a measured F[site, t]: one tap per (site, t).

    Mirrors the documented retrocausal-echo-v1 tap map: delay = t * step, signed amplitude = Re F
    (theta_z = 0 so F is real; negative = inverted echo), site -> constant-power pan, each tap scaled 1/n_sites.
    """
    n, depth = F.shape
    step = int(round(step_s * sr))
    ir = np.zeros((step * depth + 1, 2))
    for t in range(1, depth + 1):
        for s in range(n):
            a = F[s, t - 1].real / n * decay ** t
            pan = s / (n - 1)
            ir[t * step, 0] += a * np.cos(pan * np.pi / 2)
            ir[t * step, 1] += a * np.sin(pan * np.pi / 2)
    return ir


def convolve_stereo(x, ir):
    """x: mono (N,) or stereo (N, 2); ir: (M, 2). Returns (N + M - 1, 2)."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    return np.stack([fftconvolve(x[:, c], ir[:, c]) for c in range(2)], axis=1)


def reverb_ir(seconds=2.4, sr=SR, seed=7, damp=3.0):
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    t = np.arange(n) / sr
    env = np.exp(-t * damp)
    ir = rng.standard_normal((n, 2)) * env[:, None]
    # darker tail: one-pole lowpass whose cutoff falls with time, approximated by blending smoothed copies
    smooth = uniform_filter1d(ir, size=12, axis=0)
    w = np.clip(t / seconds, 0, 1)[:, None]
    ir = ir * (1 - w) + smooth * w
    ir[: int(0.012 * sr)] = 0
    return ir / np.sqrt((ir ** 2).sum(axis=0, keepdims=True))


def fade(x, sr=SR, fin=0.0, fout=0.0):
    x = x.copy()
    if fin > 0:
        k = min(len(x), int(fin * sr))
        x[:k] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, k)))[:, None]
    if fout > 0:
        k = min(len(x), int(fout * sr))
        x[len(x) - k:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, k)))[:, None]
    return x


def limiter(x, ceiling_db=-1.5, lookahead_s=0.005, release_s=0.08, sr=SR):
    c = 10 ** (ceiling_db / 20)
    peak = np.abs(x).max(axis=1)
    g = np.minimum(1.0, c / np.maximum(peak, 1e-12))
    L = max(1, int(lookahead_s * sr))
    g = minimum_filter1d(g, size=2 * L + 1)
    g = uniform_filter1d(g, size=L)
    g = np.minimum(g, minimum_filter1d(np.minimum(1.0, c / np.maximum(peak, 1e-12)), size=1))
    R = max(1, int(release_s * sr))
    g = np.minimum(g, uniform_filter1d(minimum_filter1d(g, size=R), size=R))
    return x * g[:, None]


def true_peak_db(x, sr=SR):
    up = resample_poly(x, 4, 1, axis=0)
    return 20 * np.log10(np.abs(up).max() + 1e-12)


def loudness(x, sr=SR):
    return pyln.Meter(sr).integrated_loudness(x)


def master(x, target_lufs=-14.0, ceiling_db=-2.0, sr=SR):
    """Gain to target loudness, limit to the ceiling, repeat until within 0.3 LU; final true-peak safety trim."""
    y = x.copy()
    for _ in range(6):
        y = y * 10 ** ((target_lufs - loudness(y, sr)) / 20)
        y = limiter(y, ceiling_db, sr=sr)
        tp = true_peak_db(y, sr)
        if tp > -1.0:
            ceiling_db -= tp + 1.0 + 0.05
            continue
        if abs(loudness(y, sr) - target_lufs) < 0.3:
            break
    tp = true_peak_db(y, sr)
    if tp > -1.0:
        y *= 10 ** ((-1.0 - tp) / 20)
    return y
