# core/: physics, measurements and the flagship piece

Produces `measurements/` (data, figures, `MEASUREMENTS.md`), `out/piece/` (the v3 video, the standalone track, the stills) and `core/ENGINES.md` (the engine census).

## Pipeline

| step | script | output | quantum or classical |
|---|---|---|---|
| 1 | `measure.py [runs…]` | `measurements/raw/<run>.json` | `otoc-echo-v1` on Atlas (aer, exact) |
| 2 | `classical.py [runs…]` | `measurements/classical/<run>.json` | classical numpy statevector (`otoc_sim.py`) |
| 3 | `analyze.py` | heatmaps, `size_study.png`, `crosscheck.png`, `summary.json`, `MEASUREMENTS.md` | classical analysis |
| 4 | `seed_midi.py` | `renders/core/midi/seed.mid` | classical: onset detection on the cooking stem |
| 5 | `midi_layer.py` | `renders/core/midi/` (`qrc.mid`, per-act blurred MIDI, `index.json`) | `qrc-midi-v1`, then `blur-midi-v1` with strength/reach taken from each act's measured F |
| 6 | `arrange.py` | `out/piece/scrambled_track.wav/.mp3`, `track_manifest.json` | classical mix of quantum-derived material |
| 7 | `piece.py` | `out/piece/scrambled_piece_v3.mp4`, `out/piece/stills/*.png` | classical compositing of `blur-v1` / `telablur-v1` frames driven by the measured F |
| 8 | `engines_census.py` | `core/ENGINES.md` | n/a |
| bg | `retro_poll.py`, `retro_submit.py`, `ab_retro.py` | `measurements/retro/` | `retrocausal-echo-v1` (one 8 s clip completed late; see below) |

Run from the repo root with `.venv\Scripts\python core\<script>.py` and ffmpeg on PATH. Every engine call goes through `moth.run`, which caches each completed job in `cache/<engine>/`. With `MODE=replay`, everything re-renders from that cache without the API.

Tests: `cd core; ..\.venv\Scripts\python -m pytest -q`. They cover the simulator (trivial, Clifford and light-cone limits), the tap-map IR and the loudness mastering.

## The piece (form 04)

1080×1350, 30 fps, 88 s. Structure (`timeline.py`):

| segment | time | data |
|---|---|---|
| intro | 0–6 s | photo A, title, how to read the strips |
| I. A circuit that cannot scramble | 6–26 s | `control_clifford_n12` (θzz = π) |
| II. A gentle drive | 26–48 s | `lowx_n12` (θx = 0.1π) |
| III. Scrambling | 48–78 s | `scrambling_n12` (θx = 0.3π) |
| end | 78–88 s | photo B, SCRAMBLED, credits and provenance |

Each of the 12 vertical strips is one qubit. At echo step t, with f = Re F(qubit, t) and loss L = 1 − |f|:

- L from 0 to 0.5 crossfades photo A along the `blur-v1` ladder.
- L from 0.5 to 1 continues along the `telablur-v1` ladder from A to photo B (scrambled eggs).
- An RdBu tint shows the sign: blue means the echo returns, red means it returns inverted.

F is not accumulated, so the finite-size revival shows on screen: around t = 15 in act III the strips sharpen and the whole eggs reappear. The panel reveals the act's measured heatmap up to the cursor and prints t and the off-kick mean |F| ("echo returning"). The video sweeps t = 1…32 across each act, so one echo step takes 0.5–0.85 s on screen. In the audio, one step is a sixteenth note at 90 bpm (167 ms).

Stills (`out/piece/stills/`): title; control at t = 20; gentle drive at t = 16; scrambling at t_sat = 9; scrambling at the revival, t = 15.5; end card.

## The track (form 02)

88 s, 48 kHz, 24-bit WAV plus 320 kbps MP3. Mastered to about −14 LUFS integrated with true peak at or below −1 dBTP (`dsp.master`). Layers:

- **Echo.** The cooking stem convolved with a tap map built from each act's measured F (`dsp.tap_ir`). The mapping follows the documented `retrocausal-echo-v1` scheme: delay = t × step, signed level = Re F / n, pan by site. All acts share one gain, so the physics sets the contrast. The control's echoes return loud and regular. The scrambling run's taps invert and cancel, leaving a quiet, diffuse wash. A gentle levelling step (dB differences between acts halved) and a 150 Hz high-pass on the echo bus are classical mix decisions.
- **Melody.** The seed MIDI is derived from the stem: spectral-flux onsets, with the dominant spectral peak snapped to D minor pentatonic. `qrc-midi-v1` re-sequences it into 128 notes. `blur-midi-v1` then blurs that melody once per act, with strength = 1 − late mean |F| and reach = the fraction of (site, t) cells the perturbation reached. Measured values: control 0.05/0.08, gentle 0.80/0.81, scrambling 0.75/0.93. The result is played by a small FM mallet synth (`synth.py`, no samples or soundfonts). It is the same melody in every act, increasingly smeared. In the control act it stays intact: 34 clear notes at full velocity across the 16 s melody window. In the gentle and scrambling acts the blur turns it into soft clouds of hundreds of quiet notes (259 and 294). The sparse, clean control melody is deliberate: it is the unscrambled reference.
- **Drone.** A quiet D/A pad under the whole piece. Reverb is synthetic and classical.

The mix was checked by measurement (spectrogram and short-term loudness, `renders/core/track_analysis.png`), not by ear. Treat the balance as a starting point for a listening pass.

## Retrocausal echo

Four `retrocausal-echo-v1` jobs from earlier in the project were polled the whole session (`retro_poll.py`, log in `measurements/retro/status_log.jsonl`). They stayed in `processing` with unchanged progress ("Rendering 26.6s through 348 taps", "Building the tap map", "waiting on aer …"). Fresh, smaller attempts (`retro_submit.py`, an 8 s clip through the measured n = 12 scrambling IR) are recorded in `measurements/retro/fresh_attempt.json`. After five failed submissions, job `e10a5f6a` completed. `ab_retro.py` compares it with the local render of the same clip and IR (`measurements/retro/ab.json`): waveform cross-correlation 0.65, envelope correlation 0.83, log-spectral distance 1.1 dB. The two are close but not sample-identical. It arrived after the track was mixed, so the track ships with the local render, labelled as such in `track_manifest.json` and the end card.
