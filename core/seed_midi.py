"""Seed MIDI from the cooking stem (classical analysis, documented in core/README.md).

1. Onsets: half-wave-rectified spectral flux of a 2048/512 STFT, adaptive median threshold, 120 ms refractory.
2. Pitch: each onset's dominant spectral peak (150 Hz - 4 kHz, 80 ms window) -> MIDI number, then snapped
   to D minor pentatonic and folded into two octaves (D3-D5). Cooking noise is not pitched; this mapping
   simply turns the brightness of each sizzle/tap into a melodic contour.
3. Velocity: onset strength (flux) scaled to 40-110. Duration: until the next onset, capped at 0.6 s.
"""
import sys
from pathlib import Path

import mido
import numpy as np
import soundfile as sf
from scipy.signal import stft, medfilt

ROOT = Path(__file__).resolve().parents[1]
SCALE = [2, 5, 7, 9, 0]          # D minor pentatonic pitch classes (D F G A C)
LO, HI = 50, 74                  # D3 .. D5


def onsets(x, sr, hop=512, n_fft=2048, refractory=0.12):
    f, t, Z = stft(x, sr, nperseg=n_fft, noverlap=n_fft - hop, boundary=None)
    mag = np.log1p(100 * np.abs(Z))
    flux = np.maximum(np.diff(mag, axis=1), 0).sum(axis=0)
    flux = flux / (flux.max() + 1e-12)
    thr = medfilt(flux, 31) + 0.06
    times, strength = [], []
    last = -1.0
    for i in range(1, len(flux) - 1):
        if flux[i] > thr[i] and flux[i] >= flux[i - 1] and flux[i] >= flux[i + 1]:
            ti = t[i + 1]
            if ti - last >= refractory:
                times.append(ti)
                strength.append(flux[i])
                last = ti
    return np.array(times), np.array(strength)


def snap(m):
    m = int(round(m))
    best = min((abs(m - c), c) for c in range(m - 6, m + 7) if c % 12 in SCALE)[1]
    while best < LO:
        best += 12
    while best > HI:
        best -= 12
    return best


def peak_pitch(x, sr, t0, win=0.08):
    a = int(t0 * sr)
    seg = x[a:a + int(win * sr)]
    if len(seg) < 256:
        return 62
    spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs = np.fft.rfftfreq(len(seg), 1 / sr)
    band = (freqs > 150) & (freqs < 4000)
    f0 = freqs[band][np.argmax(spec[band])]
    return 69 + 12 * np.log2(f0 / 440.0)


def notes_from_stem(path, max_dur=0.6):
    x, sr = sf.read(path, always_2d=True)
    x = x.mean(axis=1)
    times, strength = onsets(x, sr)
    notes = []
    for i, t0 in enumerate(times):
        dur = min((times[i + 1] - t0) if i + 1 < len(times) else max_dur, max_dur)
        vel = int(np.clip(40 + 70 * strength[i] / (strength.max() + 1e-12), 1, 127))
        notes.append((float(t0), float(max(dur, 0.08)), snap(peak_pitch(x, sr, t0)), vel))
    return notes


def write_midi(notes, path, bpm=90, tpb=480):
    mid = mido.MidiFile(ticks_per_beat=tpb)
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=0))
    tr.append(mido.MetaMessage("track_name", name="cooking-stem seed", time=0))
    sec2tick = tpb * bpm / 60.0
    events = []
    for t0, d, p, v in notes:
        events.append((round(t0 * sec2tick), 1, p, v))
        events.append((round((t0 + d) * sec2tick), 0, p, 0))
    events.sort()
    now = 0
    for tick, on, p, v in events:
        tr.append(mido.Message("note_on" if on else "note_off", note=p, velocity=v, time=tick - now))
        now = tick
    mid.save(path)
    return path


if __name__ == "__main__":
    stem = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "media" / "stem_full.wav"
    out = ROOT / "renders" / "core" / "midi"
    out.mkdir(parents=True, exist_ok=True)
    notes = notes_from_stem(stem)
    write_midi(notes, out / "seed.mid")
    print(len(notes), "notes; pitches", sorted(set(n[2] for n in notes)), "span", notes[0][0], notes[-1][0])
