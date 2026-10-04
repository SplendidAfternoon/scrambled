"""otoc-echo-v1 result -> F[site, t] complex array, plus summaries and heatmaps."""
import json
import sys
from pathlib import Path

import numpy as np


def load_F(rec):
    out = rec["response"]["result"]["output"]
    s = out["data"]["series"]
    F = np.array(s["F_re"]) + 1j * np.array(s["F_im"])
    return F, out["extras"]


def summary(F, extras):
    absF = np.abs(F)
    k = extras["kick_site"]
    cone = np.array(extras["light_cone"])
    arrival = [int(np.argmax(row)) + 1 if row.any() else None for row in cone]
    others = np.delete(absF, k, axis=0)
    mean_t = others.mean(axis=0)
    tail = mean_t[len(mean_t) // 2:]
    return {
        "shape": list(F.shape),
        "kick_site": k,
        "light_cone_arrival_t": arrival,
        "mean_absF_offkick_by_t": [round(float(x), 3) for x in mean_t],
        "late_mean": round(float(tail.mean()), 3),
        "late_std": round(float(tail.std()), 3),
        "summary": extras["summary"],
    }


def heatmaps(named, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, len(named), figsize=(6 * len(named), 4), squeeze=False)
    for ax, (name, F) in zip(axes[0], named.items()):
        im = ax.imshow(F.real, aspect="auto", cmap="RdBu", vmin=-1, vmax=1,
                       extent=[0.5, F.shape[1] + 0.5, F.shape[0] - 0.5, -0.5])
        ax.set_title(f"{name}: Re F(site, t)")
        ax.set_xlabel("echo step t")
        ax.set_ylabel("site")
    fig.colorbar(im, ax=axes[0].tolist(), shrink=0.8)
    fig.savefig(path, dpi=120, bbox_inches="tight")


if __name__ == "__main__":
    named = {}
    for p in sys.argv[1:]:
        rec = json.loads(Path(p).read_text(encoding="utf-8"))
        F, ex = load_F(rec)
        name = Path(p).stem.replace("otoc_", "")
        named[name] = F
        print(name, json.dumps(summary(F, ex)))
    heatmaps(named, Path("probes") / "heatmaps_m0.png")
