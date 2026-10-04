# Why you can't unscramble an egg (quantum edition) — script

One concept: **information scrambling** (nicknamed the "quantum butterfly effect", a metaphor), shown with real
out-of-time-order-correlator (OTOC) data measured on Moth Quantum's Atlas platform
(`otoc-echo-v1`, aer emulator). Audience: curious general public, no maths assumed.

Format: 1920×1080, 30 fps, captions burned in. The narration lines below (blockquotes, `>`)
are the single source of truth: `make_explainer.py` reads them for the placeholder voice and the
captions, so editing this file and re-running the script updates both. Each `>` line is one
caption card.

Visual notes are for the animation; the bracketed `[data: …]` notes say which measured array is on
screen.

---

## 1. The egg

Visual: photo of whole eggs in the pan morphs into the scrambled-egg photo through the
`telablur-v1` ladder (Atlas image engine). Title card on the right.

> Crack an egg into a pan and stir.
> Nothing is lost: every bit of yolk is still in there.
> But you will never stir it back.
> The information about where the yolk was hasn't vanished. It has spread out.

## 2. Twelve qubits

Visual: a row of 12 egg-shaped qubits appears. The middle one (site 6) gets a nudge.

> Qubits do something similar. We simulated twelve on Moth's Atlas platform, with an emulator, not a real quantum chip.
> We give the middle one a tiny nudge.

## 3. The echo test

Visual: four steps light up in turn: run forward, nudge, run backward, compare with a run
that had no nudge. Colour legend for F.
[data: definition only — F(site, t) = echo with nudge ÷ echo without nudge]

> To see where the nudge goes, we run an echo test.
> Run the qubits forward a few steps, nudge the middle one, then run the same steps backwards.
> With no nudge, every qubit would come home exactly. So we score each qubit with a number, F.
> One means the nudge never reached it. Near zero: its trace is smeared across many qubits. Negative: flipped.
> Physicists call this an out-of-time-order correlator, or OTOC.

## 4. The light cone

Visual: the scrambling map is revealed step by step, t = 1…8, with the light-cone outline.
[data: `probes/otoc_scrambling.json` → Re F(site, t), `extras.light_cone`]

> Now watch the nudge spread.
> Each step, it can reach at most one more neighbour on each side.
> That makes a cone shape, called a light cone. After six steps it reaches both ends of the row.

## 5. The control

Visual: control map revealed t = 1…32. Every row stays at +1, the kicked row stays at −1.
[data: `probes/otoc_control_clifford.json` (theta_zz = π)]

> First, a control.
> We turn one dial so the two-qubit gate becomes a Clifford gate: a special, predictable kind.
> Now the nudge never spreads at all.
> Every other qubit comes back perfectly; the middle one just flips. Nothing is scrambled.

## 6. Scrambling

Visual: full scrambling map revealed t = 1…32; the egg row is coloured by the current column.
[data: `probes/otoc_scrambling.json` (theta_zz = 0.35π)]

> Now the scrambling setting.
> Inside the cone, the echoes fade toward zero, and many turn negative.
> The information isn't destroyed; every step can still be run backwards.
> But it's hidden in patterns shared by many qubits, so no single qubit can show it.
> That is scrambling, nicknamed the quantum butterfly effect. Only a metaphor.

## 7. The honest wobble

Visual: average |F| away from the nudged qubit vs step, for the control, the scrambling setting,
and the same chain with an added z-field; the band t = 13…16 is highlighted.
[data: mean over the 11 un-kicked sites of |F(site, t)|; z-field run = cached otoc-echo-v1 job 7a4ccdfa (theta_z = 0.25π)]

> Around step thirteen to sixteen, part of the echo comes back.
> This simple chain is exactly solvable: signals bounce off the ends and partly return.
> Add one more field, also computed on Atlas, and the chain is no longer solvable. The echo fades and settles, with no revival.

## 8. Why it matters

Visual: three cards — black holes, quantum chaos, testing quantum computers.

> Why care?
> Black holes are thought to be nature's fastest scramblers, and echo tests help physicists study that idea.
> The same measurement helps tell chaotic quantum systems from solvable ones, as you just saw.
> And it helps check that a quantum computer is doing genuinely complex quantum work.

## 9. Made on Moth Atlas

Visual: control and scrambling maps side by side, job ids, credits.

> These maps are real results from Moth Quantum's Atlas platform: the otoc-echo engine, on a noiseless emulator.
> Same recipe, two settings: in one the nudge stays put, in the other it scrambles.
> That's why you can't unscramble an egg.
