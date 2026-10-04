"""Arrange the SCRAMBLED track (classical mixing of quantum-derived material) -> out/piece/scrambled_track.wav/.mp3.

Layers per act (timeline.py):
  echo   : the cooking stem convolved with a tap map built from that act's measured F(site, t) (dsp.tap_ir).
           One common gain for all acts, so the physics sets the contrast: the Clifford control returns loud,
           regular echoes; the scrambling run's taps invert and cancel, leaving a quiet diffuse wash.
  melody : the qrc-midi-v1 re-sequenced seed melody, blurred by blur-midi-v1 with that act's F-derived
           strength, rendered by core/synth.py. The same melody each act, increasingly smeared.
  drone  : a soft D/A pad under the whole piece (classical, constant).
If retrocausal-echo-v1 outputs exist (renders/core/retro/*.wav) they are reported for A/B by core/ab_retro.py.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfiltfilt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))
import dsp  # noqa: E402
import synth  # noqa: E402
from data import F_of  # noqa: E402
from timeline import CARD_S, DURATION, SEGMENTS, STEM_WINDOW, STEP_S, XFADE_S  # noqa: E402

SR = dsp.SR
OUT = ROOT / "out" / "piece"
MIDI = ROOT / "renders" / "core" / "midi"
ECHO_DECAY = 0.97      # per-step amplitude shaping of the tap map (classical, applied equally to all acts)
TAIL_S = 2.5
MELODY_GAIN = 0.3
LEVELLING = 0.5
ECHO_HP = butter(2, 150, "highpass", fs=SR, output="sos")   # keep the echo bus out of the low end
ECHO_SUM = 3.2         # summed |tap| gain of the control tap map per channel; every act shares this gain


def stem():
    x, sr = sf.read(ROOT / "media" / "stem_full.wav", always_2d=True)
    assert sr == SR, sr
    return sosfiltfilt(butter(2, 70, "highpass", fs=SR, output="sos"), x.mean(axis=1))


def place(buf, x, t0):
    a = int(round(t0 * SR))
    if a >= len(buf):
        return
    x = x[: len(buf) - a]
    buf[a:a + len(x)] += x


def act_midi(act):
    idx = json.loads((MIDI / "index.json").read_text(encoding="utf-8"))
    if act in idx:
        return ROOT / idx[act]["file"], idx[act]
    return None, None


def build(allow_classical=False):
    dry_all = stem()
    total = np.zeros((int(DURATION * SR) + SR, 2))
    melody_bus = np.zeros_like(total)
    manifest = {"echo_renderer": "local tap-map convolution (core/dsp.py tap_ir), the documented "
                                 "retrocausal-echo-v1 mapping; retrocausal-echo-v1 itself did not complete "
                                 "(measurements/retro/)",
                "sources": {}, "midi": {}, "gains": {}}

    # common echo gain: normalise by the control tap map's total signed weight, so 1.0 = "everything returns"
    Fc, _ = F_of("control_clifford_n12")
    g_echo = ECHO_SUM / np.abs(dsp.tap_ir(Fc, STEP_S, decay=ECHO_DECAY)).sum(axis=0).max()
    manifest["gains"]["echo"] = float(g_echo)

    acts = []
    for name, t0, t1, run in SEGMENTS:
        w0, _ = STEM_WINDOW[name]
        seg_len = t1 - t0
        # each segment's dry stem runs XFADE_S past its end so neighbouring segments overlap, not dip
        dry = dry_all[int(w0 * SR):int(w0 * SR) + int((seg_len + XFADE_S) * SR)]
        dry_st = np.stack([dry, dry], axis=1)
        if run is None:
            part = dsp.fade(dry_st * 0.5, fin=3.0 if name == "intro" else XFADE_S,
                            fout=4.0 if name == "end" else XFADE_S)
            place(total, part, t0)
            continue
        F, ex = F_of(run, allow_classical=allow_classical)
        manifest["sources"][name] = {"run": run, "source": ex["source"], "job_id": ex.get("job_id")}
        ir = dsp.tap_ir(F, STEP_S, decay=ECHO_DECAY) * g_echo
        wet = dsp.convolve_stereo(dry, ir)[: int((seg_len + TAIL_S) * SR)]
        wet = sosfiltfilt(ECHO_HP, wet, axis=0)
        part = np.zeros_like(wet)
        part[: len(dry_st)] += 0.42 * dry_st[: len(part)]
        part += wet
        part = dsp.fade(part, fin=XFADE_S, fout=TAIL_S)
        acts.append((name, t0, seg_len, part))

    # classical levelling: halve the act-to-act loudness differences in dB (order and contrast are kept)
    rms = {n: np.sqrt((p[: int(s * SR)] ** 2).mean()) for n, _, s, p in acts}
    ref = np.exp(np.mean(np.log(list(rms.values()))))
    for name, t0, seg_len, part in acts:
        g = (ref / rms[name]) ** LEVELLING
        manifest["gains"][f"level_{name}"] = round(float(20 * np.log10(g)), 2)
        place(total, part * g, t0)

        mid, info = act_midi(name)
        if mid is not None:
            notes = [n for n in synth.midi_notes(mid) if n[0] < seg_len - CARD_S - 1.0]
            mel = synth.render(notes, seg_len - CARD_S + 2.0, voice="mallet")
            place(melody_bus, dsp.fade(mel, fout=2.0) * MELODY_GAIN, t0 + CARD_S)
            manifest["midi"][name] = {"file": str(mid.relative_to(ROOT)), "job_id": info["job_id"],
                                      "params": info["params"], "notes": len(notes),
                                      "melody_window_s": round(seg_len - CARD_S - 1.0, 2),
                                      "last_note_s": round(max(n[0] for n in notes), 2) if notes else None}

    # drone: D2 + A2 + D3 pad across the whole piece
    drone_notes = [(0.0, DURATION - 3.0, p, 70) for p in (38, 45, 50)]
    drone = synth.render(drone_notes, DURATION + 1, voice="pad", pan_span=0.5)
    drone = dsp.fade(drone, fin=4.0, fout=5.0) * 0.07
    place(total, drone, 0.0)

    rev = dsp.reverb_ir()
    mel_wet = dsp.convolve_stereo(melody_bus, rev)[: len(total)]
    total += melody_bus + 0.35 * mel_wet
    tot_wet = dsp.convolve_stereo(total, rev)[: len(total)]
    total = total + 0.12 * tot_wet
    total = total[: int(DURATION * SR)]
    total = dsp.fade(total, fin=0.05, fout=3.0)

    # gentle high-pass (remove DC / sub rumble below ~30 Hz)
    total = sosfiltfilt(butter(2, 30, "highpass", fs=SR, output="sos"), total, axis=0)
    mastered = dsp.master(total)
    manifest["loudness_lufs"] = round(dsp.loudness(mastered), 2)
    manifest["true_peak_dbtp"] = round(dsp.true_peak_db(mastered), 2)
    manifest["duration_s"] = round(len(mastered) / SR, 3)
    return mastered, manifest


def main(allow_classical=False):
    OUT.mkdir(parents=True, exist_ok=True)
    y, manifest = build(allow_classical)
    wav = OUT / "scrambled_track.wav"
    sf.write(wav, y, SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "320k",
                    "-id3v2_version", "3", "-metadata", "title=SCRAMBLED", "-metadata",
                    "comment=Measured OTOC (otoc-echo-v1, Moth Atlas aer emulator) as echo; classical mix",
                    str(OUT / "scrambled_track.mp3")], check=True)
    (OUT / "track_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main(allow_classical="--allow-classical" in sys.argv)
