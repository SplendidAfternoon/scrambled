"""Spectrogram + short-term loudness plot of a rendered track, with act boundaries (for inspection without listening)."""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pyloudnorm as pyln  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import spectrogram  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from timeline import SEGMENTS  # noqa: E402


def main(path, out):
    x, sr = sf.read(path, always_2d=True)
    mono = x.mean(axis=1)
    f, t, S = spectrogram(mono, sr, nperseg=4096, noverlap=3072)
    meter = pyln.Meter(sr, block_size=0.4)
    hop = int(0.5 * sr)
    st = []
    for a in range(0, len(x) - int(3 * sr), hop):
        st.append(meter.integrated_loudness(x[a:a + int(3 * sr)]) if np.abs(x[a:a + int(3 * sr)]).max() > 1e-5 else -70)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(14, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    a1.pcolormesh(t, f, 10 * np.log10(S + 1e-12), shading="auto", cmap="magma", vmin=-110, vmax=-30)
    a1.set_yscale("symlog", linthresh=200)
    a1.set_ylim(30, 16000)
    a1.set_ylabel("Hz")
    a2.plot(np.arange(len(st)) * 0.5 + 1.5, st, color="k")
    a2.set_ylabel("short-term LUFS (3 s)")
    a2.set_xlabel("time (s)")
    for name, t0, t1, _ in SEGMENTS:
        for ax in (a1, a2):
            ax.axvline(t0, color="c", lw=1)
        a1.text(t0 + 0.3, 12000, name, color="w")
    a1.set_title(Path(path).name)
    fig.savefig(out, dpi=90, bbox_inches="tight")
    print(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
