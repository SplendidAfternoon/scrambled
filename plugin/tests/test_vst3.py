"""End-to-end check of the built VST3: load it in a host (pedalboard) and verify that its impulse response
is the measured tap map from the bundled preset JSON (delay = t/depth * Time, gain = |F| with sign of Re F,
constant-power pan = site/(n_sites-1), wet normalised by 1/sqrt(sum F^2)).

    .venv\\Scripts\\python plugin\\tests\\test_vst3.py
"""
import json
import os
import sys
from pathlib import Path

import numpy as np
import pedalboard

PLUGIN = Path(__file__).resolve().parents[1]
VST3 = PLUGIN / "dist" / "ScrambledEcho.vst3" / "Contents" / "x86_64-win" / "ScrambledEcho.vst3"
SR = 48000
failures = []


def check(cond, msg):
    print(("ok   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def expected_steps(preset, commutator=False):
    """Per echo step t: (left, right) sums of the normalised taps, straight from the preset JSON.
    commutator: gain C = (1 - Re F)/2 on every grid cell (cells absent from the list have F = 0)."""
    n, depth = preset["n_sites"], preset["depth"]
    g = {}
    if commutator:
        g = {(s, t): 0.5 for s in range(n) for t in range(1, depth + 1)}
    for tap in preset["taps"]:
        mag = float(np.hypot(tap["F_re"], tap["F_im"]))
        g[(tap["site"], tap["depth"])] = (1 - tap["F_re"]) / 2 if commutator else (-mag if tap["F_re"] < 0 else mag)
    norm = 1 / np.sqrt(sum(v * v for v in g.values()))
    out = np.zeros((depth + 1, 2))
    for (site, t), v in g.items():
        ang = site / (n - 1) * np.pi / 2
        out[t] += v * norm * np.array([np.cos(ang), np.sin(ang)])
    return out


def impulse_response(p, seconds):
    x = np.zeros((2, int(seconds * SR)), np.float32)
    x[:, 0] = 1.0
    p.reset()
    return p.process(x, SR, reset=True)


def reset_edits(p):
    p.split = 0.0
    for s in range(12):
        setattr(p, f"site_{s}_split", 0.0)
        setattr(p, f"site_{s}_gain_db", 0.0)


def egg_edits(p, presets):
    """Egg drags: per-site split and gain parameters, and the global Split macro."""
    names = set(p.parameters)
    want = {"split"} | {f"site_{s}_split" for s in range(12)} | {f"site_{s}_gain_db" for s in range(12)}
    check(want <= names, "exposes Split macro + 12 site split + 12 site gain parameters (automatable)")
    g = p.parameters["site_3_gain_db"]
    check(abs(g.min_value - -24) < 1e-6 and abs(g.max_value - 6) < 1e-6, f"site gain range {g.min_value}..{g.max_value} dB")

    ctl = json.loads(presets[0].read_text(encoding="utf-8"))
    p.map = "Control (Clifford)"
    p.view = "F (echo survives)"
    p.scramble = 100.0
    p.mix = 100.0
    p.feedback = 0.0
    p.width = 100.0
    p.sync = False
    p.time_ms = 1000.0
    reset_edits(p)
    base = impulse_response(p, 1.8)

    # Site 11 at -24 dB: the right channel loses exactly (1 - 10^(-24/20)) of site 11's taps.
    p.site_11_gain_db = -24.0
    y = impulse_response(p, 1.8)
    p.site_11_gain_db = 0.0
    step = SR / ctl["depth"]
    norm = 1 / np.sqrt(sum(float(np.hypot(t["F_re"], t["F_im"])) ** 2 for t in ctl["taps"]))
    err = 0.0
    for tap in (t for t in ctl["taps"] if t["site"] == 11):
        c = int(np.floor(tap["depth"] * step))
        mag = float(np.hypot(tap["F_re"], tap["F_im"])) * (-1 if tap["F_re"] < 0 else 1)
        diff = float((base[1, c - 2:c + 3] - y[1, c - 2:c + 3]).sum())
        err = max(err, abs(diff - (1 - 10 ** (-24 / 20)) * mag * norm))
    left_same = float(np.abs(base[0] - y[0]).max())
    check(err < 2e-3 and left_same < 1e-5, f"site 11 gain -24 dB scales only that site (err {err:.1e}, left change {left_same:.1e})")

    # Site 0 split 100 %: its delays stretch by 1.5 (edge site), so the last echo moves from 1.0 s to 1.5 s.
    p.site_0_split = 100.0
    y = impulse_response(p, 1.8)
    last_l = int(np.nonzero(np.abs(y[0]) > 1e-6)[0][-1])
    check(abs(last_l - 1.5 * SR) <= 3, f"site 0 split 100 %: last left echo at {last_l / SR:.4f} s (expect 1.5000)")
    p.site_0_split = 0.0

    # Split macro moves every site off the shell; at 0 the IR is the measured map again.
    p.split = 100.0
    y = impulse_response(p, 1.8)
    moved = float(np.abs(y - base).max())
    p.split = 0.0
    y = impulse_response(p, 1.8)
    back = float(np.abs(y - base).max())
    check(moved > 0.05 and back < 1e-6, f"Split macro changes the IR ({moved:.2f}) and 0 % restores it ({back:.1e})")


def state_round_trip(p):
    """Edits survive a host save/load (Ableton stores the VST3 state blob)."""
    p.map = "Kick left (site 2)"
    p.scramble = 80.0
    p.time_ms = 700.0
    p.split = 25.0
    p.site_2_split = 60.0
    p.site_9_gain_db = -9.0
    p.process(np.zeros((2, 512), np.float32), SR, reset=False)
    blob = p.raw_state
    ref = impulse_response(p, 1.2)
    q = pedalboard.load_plugin(os.fspath(VST3))
    q.raw_state = blob
    q.process(np.zeros((2, 512), np.float32), SR, reset=False)
    same = (q.map == p.map and abs(q.split - 25.0) < 1e-3 and abs(q.site_2_split - 60.0) < 1e-3
            and abs(q.site_9_gain_db - -9.0) < 1e-3 and abs(q.time_ms - p.time_ms) < 1e-3)
    check(same, f"state round trip restores params (map {q.map}, split {q.split}, s2 {q.site_2_split}, s9 {q.site_9_gain_db} dB)")
    y = impulse_response(q, 1.2)
    check(float(np.abs(y - ref).max()) < 1e-6, f"restored instance renders the same IR (max diff {np.abs(y - ref).max():.1e})")
    reset_edits(p)


def main():
    p = pedalboard.load_plugin(os.fspath(VST3))
    check(p.name == "Scrambled Echo", f"loads as '{p.name}'")
    names = set(p.parameters)
    check({"map", "sync", "time_ms", "division", "mix", "feedback", "scramble", "width", "view"} <= names,
          "exposes Map, Sync, Time, Division, Mix, Feedback, Scramble, Width, View")
    presets = sorted((PLUGIN / "presets").glob("*.json"))
    labels = p.parameters["map"].valid_values
    check(len(labels) == len(presets) + 1 and labels[-1] == "Custom JSON", f"map menu {labels}")

    p.sync = False
    p.mix = 100.0
    p.feedback = 0.0
    p.width = 100.0
    p.scramble = 100.0
    p.time_ms = 1000.0
    train_ms = float(p.time_ms)
    for path in presets:
        pre = json.loads(path.read_text(encoding="utf-8"))
        p.map = pre["name"]
        y = impulse_response(p, train_ms / 1000 + 0.5)
        exp = expected_steps(pre)
        step = train_ms / 1000 * SR / pre["depth"]
        worst = 0.0
        for t in range(1, pre["depth"] + 1):
            c = t * step
            lo, hi = int(np.floor(c)) - 2, int(np.floor(c)) + 3
            got = y[:, lo:hi].sum(axis=1)
            worst = max(worst, float(np.abs(got - exp[t]).max()))
        stray = y.copy()
        for t in range(1, pre["depth"] + 1):
            c = int(np.floor(t * step))
            stray[:, c - 2:c + 3] = 0
        check(worst < 2e-3 and np.abs(stray).max() < 1e-4,
              f"{pre['name']:20s} IR matches preset taps (max err {worst:.1e}, stray {np.abs(stray).max():.1e})")

    # View C: gains are the normalised squared commutator of the same measured map.
    for name in ("Scrambling", "Edge kick, sparse (site 0)"):
        pre = next(json.loads(q.read_text(encoding="utf-8")) for q in presets
                   if json.loads(q.read_text(encoding="utf-8"))["name"] == name)
        p.map = name
        p.view = "C (operator spread)"
        y = impulse_response(p, train_ms / 1000 + 0.5)
        exp = expected_steps(pre, commutator=True)
        step = train_ms / 1000 * SR / pre["depth"]
        err = max(float(np.abs(y[:, int(t * step) - 2:int(t * step) + 3].sum(axis=1) - exp[t]).max())
                  for t in range(1, pre["depth"] + 1))
        check(err < 2e-3, f"View C on {name}: IR = (1 - Re F)/2 map (max err {err:.1e})")
    p.view = "F (echo survives)"

    # Scramble = 0 must give the Control (Clifford) map whatever Map is selected.
    ctl = json.loads(presets[0].read_text(encoding="utf-8"))
    p.map = "Scrambling"
    p.scramble = 0.0
    y = impulse_response(p, train_ms / 1000 + 0.5)
    step = train_ms / 1000 * SR / ctl["depth"]
    exp = expected_steps(ctl)
    err = max(float(np.abs(y[:, int(t * step) - 2:int(t * step) + 3].sum(axis=1) - exp[t]).max())
              for t in range(1, ctl["depth"] + 1))
    check(err < 2e-3, f"Scramble 0 % on Scrambling = Control map (max err {err:.1e})")

    # Feedback stays bounded and decays at maximum on the densest map.
    p.map = "Control (Clifford)"
    p.scramble = 100.0
    p.feedback = 95.0
    p.time_ms = 200.0
    noise = (np.random.default_rng(1).standard_normal((2, SR)) * 0.3).astype(np.float32)
    x = np.concatenate([noise, np.zeros((2, SR * 30), np.float32)], axis=1)
    y = p.process(x, SR, reset=True)
    last = float(np.sqrt(np.mean(y[:, -SR:] ** 2)))
    check(np.isfinite(y).all() and np.abs(y).max() < 4 and last < 1e-3,
          f"Feedback 95 % bounded (peak {np.abs(y).max():.2f}) and decays (last-second rms {last:.1e})")

    # Sync: Division 1/4 at the host's (or fallback) 120 BPM puts the t = depth echo at 0.5 s.
    p.feedback = 0.0
    p.mix = 100.0
    p.map = "Control (Clifford)"
    p.sync = True
    p.division = "1/4"
    y = impulse_response(p, 1.0)
    last = int(np.nonzero(np.abs(y).sum(axis=0) > 1e-6)[0][-1])
    check(abs(last - SR // 2) <= 2, f"Sync 1/4 at 120 BPM: last echo at {last / SR:.4f} s (expect 0.5000)")
    p.sync = False

    # Other sample rates and odd block sizes: the t = depth echo still lands on Time.
    p.time_ms = 500.0
    t_ms = float(p.time_ms)
    for sr, block in ((44100, 7), (96000, 4096), (22050, 333)):
        x = np.zeros((2, int(sr * 0.8)), np.float32)
        x[:, 0] = 1.0
        y = p.process(x, sr, buffer_size=block, reset=True)
        last = int(np.nonzero(np.abs(y).sum(axis=0) > 1e-6)[0][-1])
        expect = t_ms / 1000 * sr
        check(abs(last - expect) <= 2 and np.isfinite(y).all(),
              f"{sr} Hz, block {block}: last echo at sample {last} (expect {expect:.0f})")

    # Dry path is untouched at Mix 0.
    p.mix = 0.0
    p.feedback = 30.0
    y = p.process(noise, SR, reset=True)
    check(float(np.abs(y - noise).max()) < 1e-5, "Mix 0 % passes the input unchanged")

    egg_edits(p, presets)
    state_round_trip(p)

    print(f"{len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
