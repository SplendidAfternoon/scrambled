"""Sound bed for out/quantum_egg.mp4, synced to the picture and driven by the same measured OTOC data.

Layers (all classical audio processing of measured data):
  1. bed      media/stem_full.wav (cooking audio) rendered through the measured otoc-echo-v1 tap map
              with ../pipeline/audio_local.render (classical multi-tap render of measured taps). The scrambling render
              plays under the echo/inside sections, its level following the measured band-mean 1-|F|; the
              Clifford-control render (|F| = 1, clean echoes) plays, quieter, under the control section.
  2. cracks   one short shell "crack" per band, at the moment that band's 1-|F| first crosses the shell's
              crack threshold (CRACK_S, same value as the shader in web/main.js), panned by site, pitched by latitude.
  3. lifts    a soft low "thunk" whenever a band's 1-|F| rises through the fragment-lift level (LIFT_S), and a
              quiet high "settle" ping when it falls back below it (the finite-size revival).
Mastering (ffmpeg loudnorm, 2 pass) to -16 LUFS integrated, true peak <= -1 dBTP.

    ..\\.venv\\Scripts\\python sound_bed.py      (from three/; needs ffmpeg on PATH)
Writes audio/*.wav, audio/events.json, out/quantum_egg.mp4 (with audio), out/quantum_egg_silent.mp4.
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))
import audio_local  # noqa: E402
import fmap  # noqa: E402

SR = 48000
DUR = 45.0
ECHO0, ECHO1 = 8.0, 32.0            # web/main.js TL.echo
INSIDE1 = 37.0                      # TL.inside end = control start
CONTROL1, END1 = 41.0, 45.0
NSTEP, NSITE = 32, 12
CRACK_S = 0.12 / 1.3                # shader: cracks open when reveal = 1.3 * s > 0.12
LIFT_S = 0.78 / 1.3                 # shader: lowest fragment-lift onset (aRand = 0) at 1.3 * s = 0.78
AUD = HERE / "audio"


def absF(name):
    rec = json.loads((ROOT / "probes" / f"otoc_{name}.json").read_text(encoding="utf-8"))
    F, _ = fmap.load_F(rec)
    return np.abs(F)


def field(A, site, tc):
    """Same interpolation as web/main.js fieldAt: tc=0 before the kick, smoothstep between steps."""
    at = lambda k: 1.0 if k <= 0 else A[site, min(k, NSTEP) - 1]  # noqa: E731
    k0 = int(np.floor(tc)); f = tc - k0; w = f * f * (3 - 2 * f)
    return at(k0) * (1 - w) + at(k0 + 1) * w


def video_time(tc):
    return ECHO0 + tc / NSTEP * (ECHO1 - ECHO0)


def crossings(A):
    """Times (video seconds) where each band's s = 1-|F| crosses CRACK_S / LIFT_S."""
    tcs = np.linspace(0, NSTEP, 32 * 400 + 1)
    ev = []
    for k in range(NSITE):
        s = np.array([1 - field(A, k, tc) for tc in tcs])
        first_crack = np.argmax(s > CRACK_S) if (s > CRACK_S).any() else None
        if first_crack is not None:
            ev.append({"type": "crack", "site": k, "t": round(video_time(tcs[first_crack]), 3)})
        above = s > LIFT_S
        for i in np.nonzero(above[1:] != above[:-1])[0] + 1:
            ev.append({"type": "lift" if above[i] else "settle", "site": k, "t": round(video_time(tcs[i]), 3)})
    return sorted(ev, key=lambda e: e["t"])


def env_curve(A):
    """Band-mean s(t) on the audio timeline (0 outside the echo, held at the final value after it)."""
    t = np.arange(int(DUR * SR)) / SR
    tc_grid = np.linspace(0, NSTEP, 2001)
    mean_grid = np.array([np.mean([1 - field(A, k, tc) for k in range(NSITE)]) for tc in tc_grid])
    tc = np.clip((t - ECHO0) / (ECHO1 - ECHO0), 0, 1) * NSTEP
    return np.interp(tc, tc_grid, mean_grid)


def fade(n, a, b, t):
    return np.clip((t - a) / max(b - a, 1e-9), 0, 1)


def pan(x, site):
    p = site / (NSITE - 1)
    return np.stack([x * np.cos(p * np.pi / 2), x * np.sin(p * np.pi / 2)], axis=1)


def crack_sound(site, rng):
    """Short bright crack: band-passed noise burst + damped ping; higher bands (top of egg) ring higher."""
    n = int(0.35 * SR); t = np.arange(n) / SR
    noise = rng.normal(size=n)
    noise = np.diff(noise, prepend=0) * np.exp(-t / 0.012)                 # click
    f0 = 1800 + (NSITE - 1 - site) * 140
    ping = np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.06) * 0.5 + np.sin(2 * np.pi * f0 * 2.76 * t) * np.exp(-t / 0.025) * 0.25
    return pan((noise * 0.6 + ping) * 0.5, site)


def lift_sound(site, up):
    n = int(0.6 * SR); t = np.arange(n) / SR
    if up:   # low soft thunk with a short pitch drop
        f = 180 + (NSITE - 1 - site) * 8
        x = np.sin(2 * np.pi * (f * t - 40 * t * t)) * np.exp(-t / 0.12) * 0.55
    else:    # quiet glassy settle ping (revival)
        f = 2600 + (NSITE - 1 - site) * 90
        x = np.sin(2 * np.pi * f * t) * np.exp(-t / 0.18) * np.minimum(t / 0.01, 1) * 0.18
    return pan(x, site)


def place(buf, clip, t0):
    i = int(t0 * SR); j = min(len(buf), i + len(clip))
    if i < len(buf):
        buf[i:j] += clip[: j - i]


def ffmpeg(*args, capture=False):
    r = subprocess.run(["ffmpeg", "-y", "-hide_banner", *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    return r.stderr


def main():
    AUD.mkdir(exist_ok=True)
    stem = ROOT / "media" / "stem_full.wav"
    scr_wav, clf_wav = AUD / "stem_taps_scrambling.wav", AUD / "stem_taps_clifford.wav"
    audio_local.render(str(stem), "scrambling", scr_wav)
    audio_local.render(str(stem), "control_clifford", clf_wav)

    def load(p):
        x, sr = sf.read(p, always_2d=True)
        assert sr == SR, sr
        x = x[: int(DUR * SR)]
        return np.pad(x, ((0, int(DUR * SR) - len(x)), (0, 0)))

    dry = load(stem)
    dry = np.repeat(dry[:, :1], 2, axis=1)
    scr, clf = load(scr_wav), load(clf_wav)
    t = np.arange(int(DUR * SR)) / SR

    A_s = absF("scrambling")
    m = env_curve(A_s)                                         # 0 .. ~0.75
    # gains (linear) per section
    g_dry = 0.9 * (1 - fade(0, ECHO0 - 1, ECHO0 + 2, t)) + 0.15 * fade(0, ECHO0 - 1, ECHO0 + 2, t)
    g_dry *= 1 - fade(0, INSIDE1 - 0.5, INSIDE1, t)
    g_scr = (0.25 + 0.75 * np.clip(m / 0.72, 0, 1)) * fade(0, ECHO0 - 1, ECHO0 + 0.5, t) * (1 - fade(0, INSIDE1 - 0.45, INSIDE1, t))
    g_clf = 0.35 * fade(0, INSIDE1 + 0.2, INSIDE1 + 1.0, t) * (1 - fade(0, CONTROL1 + 0.5, END1, t))
    g_dry_end = 0.25 * fade(0, CONTROL1, CONTROL1 + 1.0, t) * (1 - fade(0, END1 - 2.5, END1, t))
    bed = dry * (g_dry + g_dry_end)[:, None] + scr * g_scr[:, None] + clf * g_clf[:, None]
    # title fade-in
    bed *= np.clip(t / 1.5, 0, 1)[:, None]

    events = crossings(A_s)
    rng = np.random.default_rng(6)
    fx = np.zeros_like(bed)
    for e in events:
        if e["t"] >= INSIDE1:
            continue
        clip = crack_sound(e["site"], rng) if e["type"] == "crack" else lift_sound(e["site"], e["type"] == "lift")
        place(fx, clip, e["t"])
    mix = bed + fx * 0.9
    mix /= np.abs(mix).max() / 0.7
    pre = AUD / "bed_premaster.wav"
    sf.write(pre, mix.astype(np.float32), SR, subtype="FLOAT")

    # control-section events must be empty (Clifford control: |F| = 1 everywhere)
    clf_events = crossings(absF("control_clifford"))
    (AUD / "events.json").write_text(json.dumps({
        "crack_threshold_s": CRACK_S, "lift_threshold_s": LIFT_S,
        "scrambling_events": events, "clifford_control_events": clf_events}, indent=1), encoding="utf-8")

    # loudness: two-pass loudnorm -> -16 LUFS, TP -1
    tgt = "I=-16:TP=-1.5:LRA=11"
    st = ffmpeg("-i", str(pre), "-af", f"loudnorm={tgt}:print_format=json", "-f", "null", "-")
    js = json.loads(st[st.rindex("{"):st.rindex("}") + 1])
    master = AUD / "quantum_egg_master.wav"
    ffmpeg("-i", str(pre), "-af",
           f"loudnorm={tgt}:measured_I={js['input_i']}:measured_TP={js['input_tp']}:measured_LRA={js['input_lra']}"
           f":measured_thresh={js['input_thresh']}:offset={js['target_offset']}:linear=true,"
           f"alimiter=limit=0.79:level=false,aresample=48000",
           "-c:a", "pcm_s24le", str(master))

    out = HERE / "out" / "quantum_egg.mp4"
    silent = HERE / "out" / "quantum_egg_silent.mp4"
    if not silent.exists():
        shutil.copy2(out, silent)
    ffmpeg("-i", str(silent), "-i", str(master), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
           "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", str(DUR), "-movflags", "+faststart", str(out))
    print("events:", len(events), "| clifford events:", len(clf_events))
    print("wrote", out)


if __name__ == "__main__":
    main()
