"""Figures + numbers for measurements/: heatmaps for every run, size study, classical cross-check, MEASUREMENTS.md.

Definitions (all on m(t) = mean over off-kick sites of |F(site, t)|):
  t_sat : first local minimum of m(t) below 0.5 (the first time the perturbation has filled the chain)
  t_rev : the maximum of m(t) in the n steps after t_sat, if it rises >= 0.1 above m(t_sat) and is not at the
          window edge (finite-size revival: the operator
          front reflects off the open ends and partially refocuses)
  v_B   : butterfly velocity, slope of distance |i - k| vs light-cone arrival (first t with |1 - F| > 0.1)
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
from data import CLASSICAL, RAW, F_of, record  # noqa: E402
from measure import RUNS  # noqa: E402

M = ROOT / "measurements"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.titlesize": 12,
                     "savefig.dpi": 200, "figure.dpi": 100})

LABEL = {"control_clifford": "Clifford control (θzz = π)", "lowx": "weak drive (θx = 0.1π)",
         "scrambling": "scrambling (θx = 0.3π)"}


def label(name):
    base, n = name.rsplit("_n", 1)
    return f"{LABEL[base]}, n = {n}"


def m_curve(F, k):
    return np.abs(np.delete(F, k, axis=0)).mean(axis=0)


def t_sat_rev(m, n_sites):
    t_sat = t_rev = None
    for i in range(1, len(m) - 1):
        if m[i] < 0.5 and m[i] <= m[i - 1] and m[i] <= m[i + 1]:
            t_sat = i
            break
    if t_sat is not None:
        win = m[t_sat + 1:min(len(m), t_sat + 1 + n_sites)]
        if len(win) and win.max() - m[t_sat] >= 0.1 and win.argmax() < len(win) - 1:
            t_rev = t_sat + 1 + int(win.argmax())
    return (t_sat + 1 if t_sat is not None else None), (t_rev + 1 if t_rev is not None else None)


def v_butterfly(F, k, tol=0.1):
    d, ta = [], []
    for i, row in enumerate(F):
        idx = np.nonzero(np.abs(row - 1) > tol)[0]
        if i != k and len(idx):
            d.append(abs(i - k))
            ta.append(idx[0] + 1)
    if len(d) < 3:
        return None
    return float(np.polyfit(ta, d, 1)[0])


def heatmap(name, F, ex, path):
    n, depth = F.shape
    fig, ax = plt.subplots(figsize=(7.2, 3.2 + 0.08 * n))
    im = ax.imshow(F.real, aspect="auto", cmap="RdBu", vmin=-1, vmax=1, interpolation="nearest",
                   extent=[0.5, depth + 0.5, n - 0.5, -0.5])
    ax.set_xlabel("echo step t")
    ax.set_ylabel("qubit (site)")
    ax.axhline(ex["kick_site"], color="k", lw=0.6, ls=":")
    src = "otoc-echo-v1 · Moth Atlas aer emulator, exact" if ex["job_id"] else "classical numpy statevector"
    ax.set_title(f"Re F(site, t) — {label(name)}\n{src}" + (f" · job {ex['job_id'][:8]}" if ex["job_id"] else ""))
    cb = fig.colorbar(im, ax=ax, pad=0.015)
    cb.set_label("F  (+1 echo returns intact, −1 inverted, 0 erased)")
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def names_available():
    names = {p.stem for p in RAW.glob("*.json") if p.stem in RUNS}
    names |= {p.stem for p in CLASSICAL.glob("*.json")}
    return sorted(names, key=lambda s: (s.rsplit("_n", 1)[0], int(s.rsplit("_n", 1)[1])))


def main():
    rows, curves, xcheck = [], {}, []
    for name in names_available():
        F, ex = F_of(name, allow_classical=True)
        k = ex["kick_site"]
        m = m_curve(F, k)
        ts, tr = t_sat_rev(m, F.shape[0])
        vb = v_butterfly(F, k)
        engine = ex["job_id"] is not None
        rec = record(name) if engine else None
        params = RUNS.get(name) or json.loads((CLASSICAL / f"{name}.json").read_text())["params"]
        row = {"name": name, "source": "engine" if engine else "classical", "n": F.shape[0],
               "theta_x/pi": round(params["theta_x"] / np.pi, 3), "theta_zz/pi": round(params["theta_zz"] / np.pi, 3),
               "job_id": ex["job_id"], "seconds": rec["seconds"] if rec else None,
               "t_sat": ts, "t_rev": tr, "v_B": None if vb is None else round(vb, 2),
               "late_mean_absF": round(float(m[16:].mean()), 3)}
        if engine:
            row["summary"] = {kk: ex["summary"][kk] for kk in ("live", "regular", "inverted", "erased")}
            cpath = CLASSICAL / f"{name}.json"
            if cpath.exists():
                c = json.loads(cpath.read_text())
                G = np.array(c["F_re"]) + 1j * np.array(c["F_im"])
                err = float(np.abs(F - G).max())
                row["classical_max_abs_err"] = err
                xcheck.append((name, F, G, err))
        rows.append(row)
        curves[name] = (m, ts, tr, engine)
        heatmap(name, F, ex, M / f"heatmap_{name}.png")

    # three-regime panel at n = 12
    trio = [n for n in ("control_clifford_n12", "lowx_n12", "scrambling_n12") if n in curves]
    fig, axes = plt.subplots(1, len(trio), figsize=(5.2 * len(trio), 4), sharey=True)
    for ax, name in zip(np.atleast_1d(axes), trio):
        F, ex = F_of(name, allow_classical=True)
        im = ax.imshow(F.real, aspect="auto", cmap="RdBu", vmin=-1, vmax=1, interpolation="nearest",
                       extent=[0.5, 32.5, F.shape[0] - 0.5, -0.5])
        ax.set_title(label(name))
        ax.set_xlabel("echo step t")
    np.atleast_1d(axes)[0].set_ylabel("qubit (site)")
    fig.colorbar(im, ax=list(np.atleast_1d(axes)), pad=0.01, label="Re F")
    fig.suptitle("Measured OTOC F(site, t) on Moth Atlas (otoc-echo-v1, aer emulator, exact) — 12-qubit chain, Z kick at site 6",
                 y=1.02)
    fig.savefig(M / "regimes_n12.png", bbox_inches="tight")
    plt.close(fig)

    # size study
    fig, ax = plt.subplots(figsize=(8, 4.2))
    cmap = plt.get_cmap("viridis")
    sizes = [n for n in curves if n.startswith("scrambling_")]
    for i, name in enumerate(sizes):
        m, ts, tr, engine = curves[name]
        c = cmap(i / max(1, len(sizes) - 1))
        ax.plot(np.arange(1, 33), m, "-o" if engine else "--", ms=3, color=c,
                label=f"n = {name.rsplit('_n', 1)[1]} ({'engine' if engine else 'classical'})")
        if ts:
            ax.plot(ts, m[ts - 1], "v", color=c, ms=8)
        if tr:
            ax.plot(tr, m[tr - 1], "^", color=c, ms=8)
    ax.set_xlabel("echo step t")
    ax.set_ylabel("mean |F| over non-kicked qubits")
    ax.set_title("Size study, scrambling regime (θx = 0.3π, θzz = 0.35π): ▼ t_sat, ▲ finite-size revival")
    ax.legend(fontsize=9, ncol=2)
    ax.grid(alpha=0.3)
    fig.savefig(M / "size_study.png", bbox_inches="tight")
    plt.close(fig)

    # classical cross-check
    if xcheck:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4))
        for name, F, G, err in xcheck:
            axes[0].plot(G.real.ravel(), F.real.ravel(), ".", ms=3, label=f"{name} (max |ΔF| = {err:.1e})")
            axes[1].semilogy(np.arange(1, 33), np.abs(F - G).max(axis=0) + 1e-17, label=name)
        axes[0].plot([-1, 1], [-1, 1], "k-", lw=0.5)
        axes[0].set_xlabel("classical numpy statevector Re F")
        axes[0].set_ylabel("otoc-echo-v1 Re F")
        axes[0].legend(fontsize=8)
        axes[1].set_xlabel("echo step t")
        axes[1].set_ylabel("max over sites |F_engine − F_numpy|")
        axes[1].legend(fontsize=8)
        fig.suptitle("Independent classical cross-check of every engine run")
        fig.savefig(M / "crosscheck.png", bbox_inches="tight")
        plt.close(fig)

    (M / "summary.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    write_md(rows, failures())
    for r in rows:
        print({k: r[k] for k in ("name", "source", "t_sat", "t_rev", "v_B", "late_mean_absF")},
              r.get("classical_max_abs_err"))


def failures():
    """Failed engine submissions, parsed from the measure logs: (run, job_id, error type, message)."""
    import re
    out = []
    for log in sorted(M.glob("measure_log*.txt")):
        raw = log.read_bytes()
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8", "replace")
        for line in text.splitlines():
            m = re.match(r"ERR (\S+) job (\S+) failed: .*?\"message\": \"(.*?)\".*?\"type\": \"(\w+)\"", line)
            if m:
                out.append((m.group(1), m.group(2), m.group(4), m.group(3).replace("\\u2014", "-")))
    return out


def retro_md():
    R = M / "retro"
    st = json.loads((R / "status.json").read_text(encoding="utf-8")) if (R / "status.json").exists() else {}
    fresh = json.loads((R / "fresh_attempt.json").read_text(encoding="utf-8")) if (R / "fresh_attempt.json").exists() else {}
    ab = json.loads((R / "ab.json").read_text(encoding="utf-8")) if (R / "ab.json").exists() else None
    L = ["Earlier `retrocausal-echo-v1` jobs, polled every 2 min by `core/retro_poll.py` "
         "(full log `measurements/retro/status_log.jsonl`):", "",
         "| job id | status | error | last progress | checked (UTC) |", "|---|---|---|---|---|"]
    for j, s in st.items():
        err = s.get("error") or {}
        L.append(f"| `{j}` | {s.get('status')} | `{err.get('type', '')}` {err.get('message', '')} | "
                 f"{(s.get('progress') or {}).get('detail', '')} | {s.get('checked')} |")
    if fresh:
        L += ["", f"Fresh attempt (`core/retro_submit.py`, 8 s clip through the measured n = 12 scrambling IR): "
              f"**{fresh.get('status')}** after {len(fresh.get('attempts', []))} failed submission(s)"
              + (f", job `{fresh['job_id']}`" if fresh.get("job_id") else "") + "."]
    inflight = R / "fresh_inflight.json"
    if inflight.exists() and not fresh.get("job_id"):
        f = json.loads(inflight.read_text(encoding="utf-8"))
        L += ["", f"Its next submission, `{f['job_id']}`, was still `{f['status']}` at {f['checked']} UTC, "
              f"stuck at \"{(f.get('progress') or {}).get('detail', '')}\" since {f['created_at']}. That is the "
              "same render-stage stall seen in the four earlier jobs, two of which ended `engine_timeout` and "
              "two `internal_error`."]
    if ab:
        L += ["", f"A/B against the local render (`measurements/retro/ab.json`): waveform cross-correlation "
              f"{ab['waveform_xcorr_max']:.2f}, envelope correlation {ab['envelope_corr']:.2f}, "
              f"log-spectral distance {ab['log_spectral_distance_db']:.1f} dB "
              f"(engine output {ab['engine_seconds']:.2f} s vs local {ab['local_seconds']:.2f} s). Same spectrum "
              "and envelope, but not sample-identical, so the engine's tap rendering differs in detail from "
              "`core/dsp.py`. The engine output arrived after the track was mixed: the track's echo layer is "
              "still the local render, as `out/piece/track_manifest.json` and the end card state."]
    else:
        L += ["", "No `retrocausal-echo-v1` output completed, so there is no A/B. The track's echo layer is the "
              "local render of the same documented tap mapping (`core/dsp.py`). `out/piece/track_manifest.json` "
              "records this, and the end card credits the mixing as classical."]
    return L + [""]


def rev_fit(sc):
    pts = [(n, r["t_rev"]) for n, r in sc.items() if r["t_rev"]]
    a, b = np.polyfit([p[0] for p in pts], [p[1] for p in pts], 1)
    by = {src: ", ".join(str(n) for n, _ in sorted(pts) if sc[n]["source"] == src) for src in ("engine", "classical")}
    over = " and ".join(f"n = {v} ({'engine-measured on Atlas' if k == 'engine' else 'classical simulator'})"
                        for k, v in by.items() if v)
    return f"{a:.2f}·n {'+' if b >= 0 else '−'} {abs(b):.1f}, over {over}"


def fmt(x):
    return "–" if x is None else x


def write_md(rows, fails):
    eng = [r for r in rows if r["source"] == "engine"]
    cls = [r for r in rows if r["source"] == "classical"]
    xc = [r for r in eng if "classical_max_abs_err" in r]
    worst = max((r["classical_max_abs_err"] for r in xc), default=None)
    L = ["# Measurements", "",
         "All quantum data in this project comes from `otoc-echo-v1` (Quantum Echo, v0.1.2) on Moth Atlas, "
         "`machine: aer` with `exact: true`: the Qiskit Aer emulator computing exact expectation values. "
         "It is not QPU hardware. Common parameters: chain lattice, depth 32, Z kick on the centre qubit "
         "(site n/2), `theta_z = 0` (so F is real), `disorder = 0`, `twirls = 1`, `min_tap_level = 0`.", "",
         "Generated by `core/analyze.py` from `measurements/raw/*.json` (engine records, as returned) and "
         "`measurements/classical/*.json` (independent numpy statevector, `core/otoc_sim.py`).", "",
         "## What is measured", "",
         "F(site, t) is the out-of-time-order correlator the engine returns as `X_kick / X_ref`: prepare |+>^n, "
         "run t Floquet layers U, apply Z to the kick qubit, run U† (t layers back), measure <X_i>. "
         "F = +1 means qubit i's echo comes back intact, −1 inverted, 0 erased. "
         "One Floquet layer is RZZ(θzz) on every neighbouring pair, then RX(θx) on every qubit "
         "(confirmed by the classical cross-check below).", "",
         "## Engine runs", "",
         "| run | n | θx/π | θzz/π | job id | wall s | t_sat | t_rev | v_B (sites/step) | late mean abs F | engine tap summary (live/regular/inverted/erased) |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in eng:
        s = r.get("summary") or {}
        L.append(f"| {r['name']} | {r['n']} | {r['theta_x/pi']} | {r['theta_zz/pi']} | `{r['job_id']}` | "
                 f"{fmt(r['seconds'])} | {fmt(r['t_sat'])} | {fmt(r['t_rev'])} | {fmt(r['v_B'])} | "
                 f"{r['late_mean_absF']} | {s.get('live')}/{s.get('regular')}/{s.get('inverted')}/{s.get('erased')} |")
    L += ["", "\"wall s\" is submit-to-result time including queueing. The Atlas queue was congested during this "
          "session (many submissions timed out before a worker picked them up), so it is not a measure of "
          "circuit cost.", "",
          "## Classical-only runs (not Atlas)", "",
          "Where the engine failed (see below) or exceeded what we waited for, the size study is extended with the "
          "classical simulator, which reproduces every engine run to ~1e-13. These rows are labelled "
          "classical everywhere they appear.", "",
          "| run | n | θx/π | θzz/π | sim s | t_sat | t_rev | v_B | late mean abs F |", "|---|---|---|---|---|---|---|---|---|"]
    for r in cls:
        sim_s = json.loads((CLASSICAL / f"{r['name']}.json").read_text())["seconds"]
        L.append(f"| {r['name']} | {r['n']} | {r['theta_x/pi']} | {r['theta_zz/pi']} | {sim_s} | {fmt(r['t_sat'])} | "
                 f"{fmt(r['t_rev'])} | {fmt(r['v_B'])} | {r['late_mean_absF']} |")
    L += ["", "## Failed engine submissions", "",
          "| run | job id | error type | message |", "|---|---|---|---|"]
    for name, jid, typ, msg in fails:
        L.append(f"| {name} | `{jid}` | `{typ}` | {msg} |")
    L += ["", "`engine_timeout` = no worker picked the job up in ~60 s (queue congestion; retryable). "
          "`execution_failed` = the engine's Aer estimator raised an error (\"aer estimator failed: \", "
          "not retryable). Identical resubmissions sometimes succeeded later (e.g. scrambling n = 16), so these "
          "look like intermittent backend failures rather than invalid parameters. n = 24 is the documented aer "
          "cap; any n = 24 row above is classical.", ""]
    sc = {r["n"]: r for r in rows if r["name"].startswith("scrambling_")}
    L += ["## Findings", "",
          "Definitions (on m(t), the mean of |F| over the non-kicked qubits): **t_sat** is the first local "
          "minimum of m(t) below 0.5, the first time the perturbation has filled the chain. **t_rev** is the "
          "maximum of m(t) in the n steps after t_sat, if it rises at least 0.1 above m(t_sat): the finite-size "
          "revival. **v_B** (butterfly velocity) is the slope of distance from the kick against light-cone "
          "arrival time (first t with |1 − F| > 0.1). The strict light cone (any nonzero change, the engine's "
          "`extras.light_cone`) always moves exactly 1 site per step, because each layer couples only nearest "
          "neighbours. v_B is smaller (≈ 0.8) because it waits for a visible change of 0.1, which arrives a "
          "little behind the strict front; the two numbers do not contradict each other.", "",
          "A caveat on the word \"scrambling\": with θz = 0 and no disorder, this kicked Ising chain is "
          "free-fermion integrable. The kick spreads and the local echoes are lost, which is what the OTOC "
          "measures and what the piece shows, but the dynamics is not chaotic and the information is not "
          "thermalised; the revivals below are one symptom. \"Scrambling\" here means operator spreading, "
          "not quantum chaos.", "",
          "1. **Clifford control (θzz = π): no scrambling.** Every non-kicked qubit has F = 1 at every step and "
          "the kicked qubit has F = −1. RZZ(π) is a product of Paulis, so it never spreads the kick.",
          "2. **Scrambling (θx = 0.3π, θzz = 0.35π).** The 0.1-threshold front moves at v_B ≈ 0.8 site per step "
          "(the strict cone moves at the circuit's maximum of 1). m(t) falls to its first minimum at t_sat ≈ "
          + ", ".join(f"{sc[n]['t_sat']} (n={n})" for n in sorted(sc) if sc[n]["t_sat"]) +
          ", then revives at t_rev ≈ "
          + ", ".join(f"{sc[n]['t_rev']} (n={n})" for n in sorted(sc) if sc[n]["t_rev"]) +
          ". The revival time grows linearly with n (least-squares fit t_rev ≈ "
          + rev_fit(sc) + "). The slope matches 1/v_B ≈ 1.2: t_rev ≈ n / v_B is the time for the operator "
          "front to travel n/2 out to the open ends and n/2 back, where it partly refocuses. This is a "
          "finite-size effect of an integrable chain, not a failure of the measurement.",
          "3. **Weak drive (θx = 0.1π, θzz = 0.35π).** Not \"loud and regular\" over 32 steps at this coupling: the "
          "front is about 3× slower (v_B ≈ 0.3 site/step), so information spreads gradually and m(t) only "
          "reaches its minimum around t ≈ 23 at n = 12. At the edges F turns negative late (t ≳ 25) when the "
          "slow front reaches the boundary. Loud, regular taps survive for the first ~8 steps.",
          "4. **Size chosen for the piece: n = 12.** All three regimes are measured on Atlas at n = 12, and its "
          "scrambling run shows the full story inside 32 steps: fast spread, saturation at t = 9, a clear revival "
          "at t = 15 and a second decay. At n = 8 the revival is noisy and the strips are coarse. At n = 16 "
          "(engine) and n = 20 (classical) the revival lands at t ≈ 20–25, leaving little room for the second "
          "decay, and the weak-drive front never reaches the edges. Twelve strips are 90 px wide at 1080 px, "
          "wide enough to read the photo through.", "",
          "## Classical cross-check", "",
          f"`core/otoc_sim.py` is an independent numpy statevector implementation of the same circuit "
          f"(Qiskit gate conventions; `core/test_otoc_sim.py` covers the trivial, Clifford and light-cone limits). "
          f"Compared with every engine run for which both exist, the largest difference over all sites and steps is "
          f"**{worst:.1e}** (floating-point round-off).", "",
          "| engine run | max abs(F_engine − F_numpy) |", "|---|---|"]
    for r in xc:
        L.append(f"| {r['name']} (`{r['job_id'][:8]}`) | {r['classical_max_abs_err']:.1e} |")
    L += ["", "Layer order matters: with RX applied before RZZ inside each layer, the error is ≈ 1.04 at n = 12. "
          "So the cross-check pins down the engine's circuit, not just its general behaviour.", "",
          "## Figures", "",
          "- `regimes_n12.png`: the three measured regimes side by side (the piece's three acts).",
          "- `size_study.png`: m(t) for every scrambling size, with t_sat and t_rev marked.",
          "- `crosscheck.png`: engine vs classical, scatter plot and per-step maximum error.",
          "- `heatmap_<run>.png`: Re F(site, t) for every run (RdBu, ±1), labelled engine/classical with job id.",
          "", "## Retrocausal echo (audio engine)", ""]
    L += retro_md()
    (M / "MEASUREMENTS.md").write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
