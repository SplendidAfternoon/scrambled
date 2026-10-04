"""Local multi-tap echo render of measured otoc-echo-v1 taps (fallback while retrocausal-echo-v1 is unavailable).

Mirrors the documented retrocausal-echo-v1 mapping: each tap is one echo; depth -> delay (master_ms / depth per step),
|F| -> level, site -> stereo pan, negative polarity -> inverted echo. Output is labelled as a local render.
"""
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).parent


def taps_of(name):
    rec = json.loads((ROOT / "probes" / f"otoc_{name}.json").read_text(encoding="utf-8"))
    ex = rec["response"]["result"]["output"]["extras"]
    return ex["taps"], ex["params"]["n_sites"], ex["params"]["depth"]


def render(stem_path, name, out_path, master_ms=6400, mix=0.6, min_level=0.02, decay=1.0):
    dry, sr = sf.read(stem_path, always_2d=True)
    dry = dry.mean(axis=1)
    taps, n_sites, depth = taps_of(name)
    step = int(sr * master_ms / 1000 / depth)
    wet = np.zeros((len(dry) + step * (depth + 1), 2))
    for t in taps:
        level = abs(complex(t["F_re"], t["F_im"])) * decay ** t["depth"]
        if level < min_level:
            continue
        sign = -1.0 if t["polarity"] < 0 else 1.0
        pan = t["site"] / (n_sites - 1)
        gl, gr = np.cos(pan * np.pi / 2), np.sin(pan * np.pi / 2)
        start = t["depth"] * step
        wet[start:start + len(dry), 0] += sign * level * gl * dry
        wet[start:start + len(dry), 1] += sign * level * gr * dry
    wet /= max(np.abs(wet).max(), 1e-9)
    out = wet * mix
    out[: len(dry)] += (1 - mix) * dry[:, None]
    out /= max(np.abs(out).max(), 1e-9) / 0.89
    sf.write(out_path, out, sr)
    return out_path


if __name__ == "__main__":
    stem = sys.argv[1] if len(sys.argv) > 1 else str(ROOT / "media" / "prep" / "stem_20s.wav")
    out_dir = ROOT / "renders" / "audio_local"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ("control_clifford", "scrambling"):
        print(render(stem, name, out_dir / f"{name}.wav"))
