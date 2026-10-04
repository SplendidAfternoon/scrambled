"""Render the audio examples THROUGH the built VST3 (loaded with Spotify's pedalboard as the host).

Every *_wet.wav is the plugin binary in plugin/dist processing the matching *_dry.wav. Parameter moves
(e.g. the Scramble sweep) are done by processing in 50 ms blocks and changing the parameter between blocks,
like host automation. Dry/wet pairs share one gain so A/B levels are honest (peak -1 dBFS for the louder).

    .venv\\Scripts\\python plugin\\tools\\render_examples.py
"""
import json
import os
from pathlib import Path

import numpy as np
import pedalboard
import soundfile as sf

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
ROOT = PLUGIN.parent
VST3 = PLUGIN / "dist" / "ScrambledEcho.vst3" / "Contents" / "x86_64-win" / "ScrambledEcho.vst3"
OUT = PLUGIN / "examples"
SR = 48000
BPM = 120.0
rng = np.random.default_rng(7)


def load_plugin():
    return pedalboard.load_plugin(os.fspath(VST3))


def set_params(p, **kw):
    for k, v in kw.items():
        setattr(p, k, v)


def process(p, dry, automation=None, block=2400):
    """dry: (2, n). automation(t_seconds) -> dict of params, applied per block."""
    p.reset()
    out = np.zeros_like(dry)
    for i in range(0, dry.shape[1], block):
        if automation:
            set_params(p, **automation(i / SR))
        out[:, i:i + block] = p.process(dry[:, i:i + block], SR, reset=False)
    return out


def write_pair(name, dry, wet, meta, index):
    g = 0.891 / max(np.abs(dry).max(), np.abs(wet).max(), 1e-9)
    sf.write(OUT / f"{name}_dry.wav", (dry * g).T, SR, subtype="PCM_16")
    sf.write(OUT / f"{name}_wet.wav", (wet * g).T, SR, subtype="PCM_16")
    index.append({"name": name, "dry": f"{name}_dry.wav", "wet": f"{name}_wet.wav", **meta})
    print(name, f"{dry.shape[1] / SR:.1f} s")


def stereo(x):
    return np.stack([x, x]).astype(np.float32)


def tail(x, seconds):
    return np.concatenate([x, np.zeros(int(seconds * SR), np.float32)])


def drum_loop(bars=4):
    beat = int(SR * 60 / BPM)
    n = beat * 4 * bars
    x = np.zeros(n, np.float32)
    t = np.arange(int(0.5 * SR)) / SR

    kick = np.sin(2 * np.pi * np.cumsum(45 + 110 * np.exp(-t * 30)) / SR) * np.exp(-t * 9)
    noise = rng.standard_normal(len(t))
    snare = (0.6 * noise * np.exp(-t * 22) + 0.5 * np.sin(2 * np.pi * 185 * t) * np.exp(-t * 18))
    hat_n = np.diff(rng.standard_normal(len(t) + 1))
    hat = hat_n * np.exp(-t * 90) * 0.35

    def put(sig, at, gain=1.0):
        end = min(n, at + len(sig))
        x[at:end] += gain * sig[:end - at]

    for b in range(4 * bars):
        at = b * beat
        if b % 4 in (0, 2) or (b % 8 == 7):
            put(kick, at if b % 8 != 7 else at + beat // 2, 0.9)
        if b % 4 in (1, 3):
            put(snare, at, 0.55)
        put(hat, at + beat // 2, 0.8)
        put(hat, at, 0.4)
    return x


def synth_line(bars=4):
    eighth = int(SR * 60 / BPM / 2)
    notes = [57, 60, 64, 67, 69, 67, 64, 60, 55, 59, 62, 67, 71, 67, 62, 59] * (bars // 2)
    n = eighth * len(notes)
    x = np.zeros(n + SR, np.float32)
    t = np.arange(int(0.45 * SR)) / SR
    for k, m in enumerate(notes):
        f = 440 * 2 ** ((m - 69) / 12)
        ph = (f * t) % 1.0
        saw = 2 * ph - 1
        env = np.exp(-t * 7) * np.minimum(1, t * 400)
        voice = saw * env
        # gentle one-pole lowpass whose cutoff falls with the envelope (plucky)
        y = np.zeros_like(voice)
        acc = 0.0
        for i in range(len(voice)):
            a = 0.04 + 0.5 * env[i]
            acc += a * (voice[i] - acc)
            y[i] = acc
        at = k * eighth
        x[at:at + len(y)] += 0.5 * y
    return x[:n]


def cooking_stem(seconds=30.0):
    x, sr = sf.read(ROOT / "media" / "stem_full.wav", always_2d=True)
    x = x.mean(axis=1)
    assert sr == SR, sr
    return x[: int(seconds * SR)].astype(np.float32)


def clap():
    t = np.arange(int(0.08 * SR)) / SR
    burst = rng.standard_normal(len(t)) * np.exp(-t * 60)
    return burst.astype(np.float32)


if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    p = load_plugin()
    index = []
    common = dict(sync=False, width=100.0, view="F (echo survives)")

    # 1. Cooking stem with Scramble automated 0 -> 100 %: the echo map morphs from the Clifford control
    #    (no scrambling) into the measured scrambling map, then back.
    dry = stereo(tail(cooking_stem(30.0), 4.0))
    set_params(p, map="Scrambling", time_ms=1600.0, mix=45.0, feedback=35.0, **common)
    wet = process(p, dry, automation=lambda s: {"scramble": float(100 * min(1.0, max(0.0, (s - 2) / 12)) if s < 17
                                                                     else 100 * max(0.0, 1 - (s - 17) / 10))})
    write_pair("01_cooking_scramble_sweep", dry, wet, {
        "source": "media/stem_full.wav (first 30 s, recorded cooking audio) + 4 s tail",
        "settings": "Map=Scrambling, Time=1600 ms, Mix=45 %, Feedback=35 %, Width=100 %, "
                    "Scramble automated 0 -> 100 % (2-14 s), held, then 100 -> 0 % (17-27 s)"}, index)

    # 2. Synthesised drum loop, tempo-synced train (1 bar at 120 BPM), kick on site 2, View C: the echoes play
    #    where the operator has spread, so they travel left -> right with the light cone.
    dry = stereo(tail(drum_loop(4), 4.0))
    set_params(p, map="Kick left (site 2)", sync=True, division="1 bar", mix=40.0, feedback=30.0, scramble=100.0,
               width=100.0, view="C (operator spread)")
    wet = process(p, dry)
    write_pair("02_drums_kick_left_C_sync", dry, wet, {
        "source": "synthesised 4-bar drum loop at 120 BPM (numpy) + 4 s tail",
        "settings": "Map=Kick left (site 2), View=C, Sync on, Division=1 bar (2.0 s: the plugin runs at 120 BPM "
                    "under pedalboard, checked in tests/test_vst3.py), Mix=40 %, Feedback=30 %, Scramble=100 %"},
               index)

    # 3. Synth arpeggio through the edge-kicked sparse chain in View C: a measured stereo ping-pong.
    line = synth_line(4)
    dry = stereo(tail(line, 5.0))
    set_params(p, map="Edge kick, sparse (site 0)", time_ms=2000.0, mix=50.0, feedback=45.0, scramble=100.0, **common)
    p.view = "C (operator spread)"
    wet = process(p, dry)
    write_pair("03_synth_edge_sparse_C", dry, wet, {
        "source": "synthesised plucked-saw arpeggio, 120 BPM eighths (numpy) + 5 s tail",
        "settings": "Map=Edge kick, sparse (site 0), View=C, Time=2000 ms, Mix=50 %, Feedback=45 %, Scramble=100 %"}, index)

    # 4. Same clap through Control (Clifford) then Scrambling: the scrambling difference in isolation.
    hit = clap()
    seg = np.zeros(int(4.0 * SR), np.float32)
    seg[: len(hit)] = hit
    dry = stereo(np.concatenate([seg, seg]))
    half = seg.shape[0] / SR
    set_params(p, map="Scrambling", time_ms=1200.0, mix=100.0, feedback=0.0, **common)
    wet = process(p, dry, automation=lambda s: {"scramble": 0.0 if s < half else 100.0})
    write_pair("04_clap_control_vs_scrambling", dry, wet, {
        "source": "two synthetic claps, 4 s apart",
        "settings": "Time=1200 ms, Mix=100 % (wet only), Feedback=0. First clap: Scramble=0 % (Control / "
                    "Clifford map: every tap |F|=1). Second clap: Scramble=100 % (measured scrambling map)."},
               index)

    # 5. One clap, wet only, View C on the edge-kicked chain: the light cone as a trajectory in time and pan.
    seg = np.zeros(int(5.0 * SR), np.float32)
    seg[: len(hit)] = hit
    dry = stereo(seg)
    set_params(p, map="Edge kick, sparse (site 0)", time_ms=3000.0, mix=100.0, feedback=0.0, scramble=100.0, **common)
    p.view = "C (operator spread)"
    wet = process(p, dry)
    write_pair("05_clap_light_cone_C", dry, wet, {
        "source": "one synthetic clap",
        "settings": "Map=Edge kick, sparse (site 0), View=C, Time=3000 ms, Mix=100 % (wet only), Feedback=0"},
               index)

    (OUT / "index.json").write_text(json.dumps({
        "plugin": "plugin/dist/ScrambledEcho.vst3 (loaded via pedalboard %s)" % pedalboard.__version__,
        "sample_rate": SR, "examples": index}, indent=2), encoding="utf-8")
