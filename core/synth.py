"""Tiny offline synth (classical): 2-operator FM mallet voice + a soft additive pad, rendering MIDI to stereo float arrays."""
import mido
import numpy as np

SR = 48000


def midi_notes(path):
    """[(start_s, dur_s, pitch, velocity)] with tempo changes honoured (mido does this in iteration)."""
    mid = mido.MidiFile(path)
    now, on, notes = 0.0, {}, []
    for msg in mid:
        now += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            on.setdefault(msg.note, []).append((now, msg.velocity))
        elif msg.type in ("note_off", "note_on"):
            if on.get(msg.note):
                t0, v = on[msg.note].pop(0)
                notes.append((t0, max(now - t0, 0.05), msg.note, v))
    return sorted(notes)


def hz(p):
    return 440.0 * 2 ** ((p - 69) / 12)


def mallet(f, dur, vel, sr=SR):
    """FM mallet: carrier f, modulator 3.5f with a fast-decaying index; ~glass marimba."""
    n = int(sr * (dur + 1.6))
    t = np.arange(n) / sr
    index = 2.4 * np.exp(-t * 9) * (vel / 127)
    env = np.exp(-t * 2.6) * (1 - np.exp(-t * 900))
    rel = np.clip(1 - (t - dur - 0.6) / 1.0, 0, 1)
    y = np.sin(2 * np.pi * f * t + index * np.sin(2 * np.pi * 3.5 * f * t))
    y += 0.25 * np.sin(2 * np.pi * 2 * f * t) * np.exp(-t * 5)
    return y * env * rel * (vel / 127) ** 1.4


def pad(f, dur, vel, sr=SR):
    n = int(sr * (dur + 1.5))
    t = np.arange(n) / sr
    att = np.clip(t / 0.35, 0, 1)
    rel = np.clip(1 - (t - dur) / 1.5, 0, 1)
    y = sum(a * np.sin(2 * np.pi * f * m * t + 0.3 * np.sin(2 * np.pi * 0.2 * t + m))
            for m, a in ((1, 1.0), (2, 0.35), (3, 0.12), (1.003, 0.5)))
    return y * att * rel * (vel / 127) * 0.35


def render(notes, length_s, voice="mallet", sr=SR, pan_span=0.7, transpose=0):
    out = np.zeros((int(length_s * sr) + 1, 2))
    fn = mallet if voice == "mallet" else pad
    for t0, d, p, v in notes:
        if t0 >= length_s:
            continue
        y = fn(hz(p + transpose), d, v, sr)
        a = int(t0 * sr)
        y = y[: len(out) - a]
        pan = 0.5 + pan_span * ((p % 12) / 11 - 0.5)
        out[a:a + len(y), 0] += y * np.cos(pan * np.pi / 2)
        out[a:a + len(y), 1] += y * np.sin(pan * np.pi / 2)
    return out
