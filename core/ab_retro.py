"""A/B: retrocausal-echo-v1 output vs the local tap-map render of the same clip and the same measured IR.

Both are peak-normalised, then compared by normalised cross-correlation (max over +-50 ms lag), short-term
envelope correlation and log-spectral distance. Writes measurements/retro/ab.json and renders/core/retro/ab_local.wav.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import correlate, welch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import dsp  # noqa: E402
from data import F_of  # noqa: E402

RETRO = ROOT / "renders" / "core" / "retro"


def local_render(clip, master_ms=5333, mix=0.6, min_level=0.02):
    x, sr = sf.read(clip)
    F, _ = F_of("scrambling_n12")
    F = np.where(np.abs(F) >= min_level, F, 0)
    ir = dsp.tap_ir(F, master_ms / 1000 / F.shape[1], sr=sr)
    wet = dsp.convolve_stereo(x, ir)
    wet /= np.abs(wet).max() + 1e-12
    out = mix * wet
    out[: len(x)] += (1 - mix) * x[:, None]
    return out / (np.abs(out).max() + 1e-12), sr


def env(y, sr, win=0.05):
    k = int(win * sr)
    m = (y ** 2).mean(axis=1) if y.ndim == 2 else y ** 2
    return np.sqrt(np.convolve(m, np.ones(k) / k, mode="valid"))[::k]


def main():
    engine = [p for p in RETRO.glob("*.wav") if "stem_8s" not in p.name and "ab_local" not in p.name]
    if not engine:
        print("no retrocausal-echo-v1 output yet")
        return None
    e, sr = sf.read(engine[0], always_2d=True)
    l, sr2 = local_render(RETRO / "stem_8s.wav")
    assert sr == sr2
    sf.write(RETRO / "ab_local.wav", l, sr)
    n = min(len(e), len(l))
    em, lm = e[:n].mean(axis=1), l[:n].mean(axis=1)
    em, lm = em / (np.abs(em).max() + 1e-12), lm / (np.abs(lm).max() + 1e-12)
    lag = int(0.05 * sr)
    xc = correlate(em, lm, mode="full")[n - 1 - lag:n + lag] / (np.linalg.norm(em) * np.linalg.norm(lm) + 1e-12)
    ee, le = env(e[:n], sr), env(l[:n], sr)
    _, pe = welch(em, sr, nperseg=4096)
    _, pl = welch(lm, sr, nperseg=4096)
    res = {"engine_file": str(engine[0].relative_to(ROOT)), "local_file": "renders/core/retro/ab_local.wav",
           "engine_seconds": len(e) / sr, "local_seconds": len(l) / sr,
           "waveform_xcorr_max": float(np.abs(xc).max()), "best_lag_ms": float((np.abs(xc).argmax() - lag) / sr * 1000),
           "envelope_corr": float(np.corrcoef(ee, le)[0, 1]),
           "log_spectral_distance_db": float(np.sqrt(np.mean((10 * np.log10((pe + 1e-15) / (pl + 1e-15))) ** 2)))}
    (ROOT / "measurements" / "retro" / "ab.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(json.dumps(res, indent=2))
    return res


if __name__ == "__main__":
    main()
