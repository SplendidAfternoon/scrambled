# Explainer: accuracy notes, sources, provenance

Deliverable for the FQxI educational category: **"Why you can't unscramble an egg (quantum edition)"**,
a 146.9 s, 1920×1080, 30 fps animated explainer that teaches information scrambling (OTOC) using three real
`otoc-echo-v1` results, all computed on the aer emulator (not quantum hardware).

| File | What |
|---|---|
| `out/scrambled_explained.mp4` | captions burned in, music bed + cooking sound, no voice |
| `out/scrambled_explained_vo.mp4` | same picture, with the placeholder voice-over and the music ducked under it |
| `out/scrambled_explained.srt` | the same captions as a sidecar subtitle file |
| `out/contact_sheet.jpg` | 12 evenly spaced frames from the VO version |
| `vo_placeholder.wav` | the placeholder voice track alone (48 kHz mono), aligned to the video timeline |
| `script.md` | beats, visual notes and narration (narration is the single source for voice and captions) |
| `make_explainer.py` | renders everything above from the probe JSON + image ladders |
| `check_outputs.py` | acceptance checks (format, duration, caption count, voice track, data identity) |

Reproduce from the repo root (ffmpeg on PATH; no API calls, no credits; about 3 minutes):

```powershell
.venv\Scripts\python edu\make_explainer.py          # add "stills" for one PNG per beat in edu/build/stills
.venv\Scripts\python edu\check_outputs.py
```

## What F means (physics check)

Source: the `otoc-echo-v1` engine docs (https://docs.mothquantum.com/llms-full.txt, "Quantum Echo", v0.1.2,
and the live schema saved at `probes/engine_otoc-echo-v1.json`):

- `kick`: "Perturbation Pauli applied to the kick site between U and U†". The circuit for echo depth t is
  forward evolution U (t Floquet layers of RX(θx) and RZZ(θzz)), a Pauli kick on the kick site, then U†
  ("Each circuit has 2·depth layers").
- `ref_floor`: "|c_ref| below which F is null". So F is normalised by a reference run without the kick.
- Checked numerically against the stored result: for both probes, `F = (X_kick + i·Y_kick) / (X_ref + i·Y_ref)`
  to machine precision (`make_explainer.py` asserts this on load). With `theta_z = 0`, F is real.

So F(site, t) is the echoed single-qubit signal at `site` with the kick, divided by the same signal
without the kick. That is a normalised out-of-time-order correlator of the form ⟨V(t)† W V(t) W⟩-type echo
(V = kick, W = probe on `site`): F = 1 when the spread operator V(t) = U†VU has not reached `site`
(they commute), and it decays/changes sign once V(t) has grown over `site`. In the video:
"+1 = the nudge never reached it", "≈0 = smeared across many", "−1 = flipped". These are plain-language
readings of that definition, not extra claims.

- `theta_zz` docs: "π is a Clifford (no scrambling)". At θzz = π, RZZ(π) = −i·Z⊗Z, itself a Pauli, so
  every layer is single-qubit rotations times a Pauli string: no entanglement is generated and the Z kick
  never grows beyond its own site. The measured control confirms it: F = +1 on all 11 other qubits at
  all 32 steps, F = −1 on the kicked qubit (the probe there anticommutes with the kick).
  **Deviation from the contract wording:** beat 5 in the contract said "information moves but isn't
  scrambled". For this control the data show the nudge does not move at all, so the narration says
  "the nudge never spreads at all" instead. Calling it a Clifford setting follows the engine docs.
- Light cone: `extras.light_cone` gives first-reachable step per site: arrival t = [6,5,4,3,2,1,1,1,2,3,4,5]
  for sites 0–11 (kick on site 6). One neighbour per step on each side; both ends reached by t = 6, which
  is what the narration says. The measured F leaves +1 only inside this cone (e.g. site 0 first drops
  at t = 6: 0.96, then 0.49).
- Scrambling run (θzz = 0.35π, θx = 0.3π): mean |F| over the 11 un-kicked sites falls from 0.83 (t=1) to
  0.24 (t=9), rises to 0.49 (t=15), then settles around 0.25 (late mean 0.253 ± 0.055). Engine summary:
  156 of 384 entries "inverted" (F < 0), 24 "erased". The narration's "fade toward zero, and many turn negative"
  matches that.
- Revival t ≈ 13–16: shown and labelled as a partial revival. The narration attributes it to a solvable,
  short chain ("signals bounce off the ends and partly return"). The timing fits: the cone reaches the ends at
  t ≈ 6, so a reflection could be back at the centre by t ≈ 12. The θz = 0.25π run of the same size shows no
  revival, which supports the integrability part of the explanation. We did not run a longer chain, so the
  finite-size part is an interpretation.
- **Integrability, not chaos (fix after the independent verifier's report).** The headline runs have θz = 0 and
  disorder 0. That makes them a kicked transverse-field Ising chain, which maps to free fermions and is exactly
  solvable (integrable). It does spread a local operator: the light cone and the decay of F are real operator
  spreading and information scrambling. It is **not** quantum chaos. So the explainer:
  - never calls the θz = 0 data chaotic. Beat 7 says "This simple chain is exactly solvable: signals bounce off
    the ends and partly return". The coherent revival fits that: free-fermion quasiparticles reflect off the
    open ends;
  - shows the non-solvable comparison from real data: the same chain with θz = 0.25π (job
    `7a4ccdfa-d29a-4e2b-a275-5dbb415a2dce`, cached at `cache/otoc-echo-v1/c534d155e09a2a92.json`). A longitudinal
    field on the kicked Ising chain breaks integrability. Its mean |F| over the 11 un-kicked qubits decays smoothly
    from 0.83 to a plateau of 0.31 ± 0.01 (t ≥ 17), with no revival, against 0.25 ± 0.06 for the solvable chain.
    That run's F is complex, so the curve uses |F|. Narration: "the chain is no longer solvable. The echo fades and
    settles, with no revival". The video does not claim this run scrambles "more" by plateau height (it doesn't).
    It also does not claim chaos for a 12-qubit run beyond calling it the non-solvable case;
  - beat 8 says OTOCs "help tell chaotic quantum systems from solvable ones, as you just saw". That is a general
    statement about the tool, illustrated by the solvable vs non-solvable pair.
- "Quantum butterfly effect" appears only as a labelled nickname. The narration says "nicknamed the quantum
  butterfly effect. Only a metaphor." and the screen shows "'quantum butterfly effect' is a nickname, a metaphor".
  The nickname comes from Shenker & Stanford, "Black holes and the butterfly effect", JHEP 03 (2014) 067.
- Emulator, not hardware: beat 2 now says "We simulated twelve on Moth's Atlas platform, with an emulator, not a real
  quantum chip". Every data beat's header says "aer emulator", and the credits say "noiseless, not hardware".
- "The information isn't destroyed; every step can still be run backwards": the dynamics is unitary and the
  emulator is noiseless (exact expectation values), so this is literally true for this data.
- Honesty labels on screen: "aer emulator" in the header of every data beat; the credits list what is quantum
  (otoc-echo-v1 on aer, blur-v1 and telablur-v1 egg frames) and what is classical (animation, compositing,
  music, captions, placeholder voice). The blur frame in the side panel is "picked by mean |F|": we choose
  which already-rendered blur-v1 frame to show from the measured curve. That choice is classical.

## "Why it matters" (beat 8): sources and how strongly it is worded

All references below were checked with a web search on 2026-10-04 (publisher or arXiv pages):

- Black holes as fastest scramblers:
  - Y. Sekino & L. Susskind, "Fast scramblers", JHEP 10 (2008) 065, arXiv:0808.2096,
    https://arxiv.org/abs/0808.2096. Conjecture 3 in the abstract: "Black holes are the fastest scramblers in
    nature". That's why the narration says "thought to be".
  - P. Hayden & J. Preskill, "Black holes as mirrors: quantum information in random subsystems", JHEP 09 (2007) 120,
    arXiv:0708.4025, https://arxiv.org/abs/0708.4025. Information thrown into a rapidly mixing black hole comes
    back out quickly, which is the motivation for scrambling.
- OTOCs as a chaos diagnostic: J. Maldacena, S. Shenker & D. Stanford, "A bound on chaos", JHEP 08 (2016) 106,
  arXiv:1503.01409 ("Chaos can be diagnosed using an out-of-time-order correlation function"). Review:
  B. Swingle, "Unscrambling the physics of out-of-time-order correlators", Nature Physics 14, 988 (2018).
  Narration: "helps tell chaotic quantum systems from solvable ones".
- OTOCs on quantum processors:
  - X. Mi et al. (Google Quantum AI), "Information scrambling in quantum circuits", Science 374, 1479–1483 (2021),
    doi:10.1126/science.abg5029. OTOCs measured on the 53-qubit Sycamore processor.
  - Google Quantum AI and Collaborators, "Observation of constructive interference at the edge of quantum
    ergodicity", Nature 646, 825 (2025), doi:10.1038/s41586-025-09526-6 ("Quantum Echoes", second-order OTOCs on
    Willow, framed by the authors as a path to verifiable quantum advantage).
  - Narration: "helps check that a quantum computer is doing genuinely complex quantum work". We claim no advantage,
    and nothing in this video ran on hardware.
- Origin of OTOCs: Larkin & Ovchinnikov (1969). This one was not re-checked; it isn't cited on screen.

## Engine jobs (all Moth Atlas; no new jobs were run for this task)

| Use | Engine | Job id | Params |
|---|---|---|---|
| Scrambling map (beats 4, 6, 7, 9) | otoc-echo-v1 | `8df5cfa2-e57c-43a8-a93a-63975efd252c` | n_sites 12, depth 32, θx 0.3π, θzz 0.35π, θz 0, kick Z @ site 6, chain, disorder 0, machine aer, exact |
| Clifford control (beats 5, 7, 9) | otoc-echo-v1 | `89c7f269-9a0c-473a-936d-a0ac2a08aa77` | same, θzz = π |
| Non-solvable comparison (beat 7 curve, beat 9 credit) | otoc-echo-v1 | `7a4ccdfa-d29a-4e2b-a275-5dbb415a2dce` | same as scrambling, plus θz = 0.25π (read from cache; no new run) |
| Egg morph, beat 1 (A → B) | telablur-v1 | strengths 0.02 `0cc32be5`, 0.05 `e69b2000`, 0.1 `789bb4a7`, 0.15 `082991be`, 0.5 `d5fe1183`, 0.85 `58b52d2c`, 0.9 `e705a08b`, 0.95 `0d276d1f`, 0.98 `a58d98ba` | image1 = whole eggs, image2 = scrambled |
| Side-panel blur ladder (beats 4–6) | blur-v1 | 0.1 `37894b70`, 0.15 `5c0e77bd`, 0.2 `e3b9ba8e`, 0.25 `ade7424d`, 0.3 `df5be01b`, 0.35 `a6de069a`, 0.4 `94b48e49` | on the whole-eggs photo (`renders/v2/index.json`, key `blurR:*`) |

The short ids above are prefixes; full ids are in `renders/v2/index.json`. Provenance in the probe JSON:
backend aer, mode emu, library_version 0.6.0, exact (shots null), seed 625476011 (irrelevant at disorder 0).

## Audio (all classical)

- Music bed: a synthesised soft pad (numpy), one chord per beat. During the scrambling beat its detune follows
  the measured 1 − mean|F| (a classical sonification choice).
- Beat 1 adds the project's own cooking recording (`media/stem_full.wav`, from 20 s).
- Placeholder voice: offline Windows SAPI ("Microsoft Zira Desktop", rate +1), one WAV per caption line,
  so captions match the voice exactly. It's a **placeholder**: to replace it, record the lines in `script.md`
  and swap `vo_placeholder.wav`. The timeline (`build/timeline.json`) gives each line's start and end.
- Both mixes are loudness-normalised with ffmpeg `loudnorm` (target −16 LUFS; measured −16.1 and −16.5).

## Known limits

- Mono audio (both inputs are mono).
- Voice is synthetic. The non-VO cut with burned captions is the one to show if no human voice is recorded.
- Gen-AI disclosure is handled by the orchestrator. Nothing in this explainer was generated by an image or video model.
