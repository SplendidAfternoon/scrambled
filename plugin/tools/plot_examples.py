"""Plot two of the rendered examples for the README: the clap through Control vs Scrambling (F view),
and the single clap through the edge-kicked chain in View C (stereo position of every echo).

    .venv\\Scripts\\python plugin\\tools\\plot_examples.py
"""
from pathlib import Path

import matplotlib
import numpy as np
import soundfile as sf

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

PLUGIN = Path(__file__).resolve().parents[1]
EX = PLUGIN / "examples"


def frames(x, sr, ms=10):
    n = int(sr * ms / 1000)
    f = x[: len(x) // n * n].reshape(-1, n, 2)
    return np.sqrt((f ** 2).mean(axis=1)), n / sr


if __name__ == "__main__":
    fig, axes = plt.subplots(2, 1, figsize=(11, 6.5))

    x, sr = sf.read(EX / "04_clap_control_vs_scrambling_wet.wav")
    t = np.arange(len(x)) / sr
    axes[0].plot(t, x[:, 0], lw=0.4, color="#2a9d8f", label="left")
    axes[0].plot(t, x[:, 1], lw=0.4, color="#e76f51", alpha=0.7, label="right")
    axes[0].axvline(4.0, color="k", lw=0.8, ls="--")
    axes[0].set_title("04: same clap, wet only. Left half: Scramble 0 % (Clifford control, every |F| = 1). "
                      "Right half: Scramble 100 % (measured scrambling map)", fontsize=9)
    axes[0].set_xlabel("time (s)")
    axes[0].legend(loc="upper right", fontsize=8)

    x, sr = sf.read(EX / "05_clap_light_cone_C_wet.wav")
    rms, dt = frames(x, sr)
    level = rms.sum(axis=1)
    pan = (rms[:, 1] - rms[:, 0]) / np.maximum(rms.sum(axis=1), 1e-9)
    tt = np.arange(len(level)) * dt
    keep = level > level.max() * 0.02
    sc = axes[1].scatter(tt[keep], pan[keep], c=level[keep], cmap="magma_r", s=8)
    axes[1].set_ylim(-1.05, 1.05)
    axes[1].set_ylabel("stereo position (L -1 .. R +1)")
    axes[1].set_xlabel("time (s)")
    axes[1].set_title("05: one clap through 'Edge kick, sparse', View C, Time 3 s: each echo's pan follows the "
                      "measured light cone (kicked at site 0, reflected at site 11)", fontsize=9)
    fig.colorbar(sc, ax=axes[1], label="level")
    fig.tight_layout()
    out = PLUGIN / "docs" / "examples.png"
    fig.savefig(out, dpi=110)
    print("saved", out.relative_to(PLUGIN))
