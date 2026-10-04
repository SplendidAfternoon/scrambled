# SCRAMBLED

Quantum information scrambling, measured on [Moth Quantum's Atlas](https://platform.mothquantum.com) and rendered as eggs.

You cannot unscramble an egg. SCRAMBLED measures the quantum version of that fact: nudge one qubit in a chain of twelve, run the circuit forward and backward, and see how much of the nudge comes back at each qubit and step. That map, an out-of-time-order correlator F(site, t) from `otoc-echo-v1`, then drives every piece in this repo: a film, a track, a 3D egg, a game, a web app, a VST plugin, a CLI, a notebook and an explainer.

**Live:** [scrambled-mu.vercel.app](https://scrambled-mu.vercel.app) (explorer + game; judges can run a real Atlas measurement without a key)

Built solo for **Moth Hack 2026** by Mana Blumicz. Everything ran on the Atlas **Qiskit Aer emulator**; compositing, mixing and rendering are classical and labelled as such.

![poster](extra/poster/scrambled_poster.jpg)

## The measurement

| Setting | What happens |
|---|---|
| Clifford control (Î¸zz = Ï€) | The nudge never spreads: every other qubit returns perfectly, the kicked one flips sign. |
| Scrambling (Î¸x = 0.3Ï€, Î¸zz = 0.35Ï€) | The nudge spreads inside a light cone, reaching both ends by step 6; echoes fade and invert; part returns around step 13â€“16 because the chain is finite. |

An independent numpy statevector reproduces every Atlas map to ~1eâˆ’13, which pins down the circuit (ZZ layer, then Rx, per Floquet step). The clean chain (Î¸z = 0) is free-fermion integrable, so "scrambling" here means operator spreading; adding a z-field (Î¸z = 0.25Ï€, also measured) removes the revival. Full study: [measurements/MEASUREMENTS.md](measurements/MEASUREMENTS.md).

## What's in the repo

| Challenge | Piece | Where |
|---|---|---|
| 01 One image, one engine | Hero image: blur-v1, strength = 1 âˆ’ late mean \|F\| | [hero/](hero/) |
| 02 Make it audible | 88 s track: cooking audio through measured echo maps, qrc-midi + blur-midi melody | [out/piece/](out/piece/), [core/](core/) |
| 03 Three dimensions | The Quantum Egg: entanglement-shader shell, cracks timed by F, blur-core interior | [three/](three/) |
| 04 Moving image | SCRAMBLED, 88 s film: twelve strips, one per qubit | [out/piece/scrambled_piece_v3.mp4](out/piece/scrambled_piece_v3.mp4) |
| 05 Quantum game | Don't Scramble the Egg, 5 levels from measured runs | [web/](web/) (`game.html`) |
| 06 Daisy Chain | 10 Atlas engines, every job id listed | [core/ENGINES.md](core/ENGINES.md), [extra/](extra/) |
| 07 VST | Scrambled Echo VST3: taps are measured OTOC maps | [plugin/](plugin/) |
| 08 Web app | SCRAMBLED Explorer: measure on Atlas from the browser | [web/](web/) (`explorer.html`) |
| 09 Quantum-native 1 | `scrambled` Python package + CLI for any image, audio or video | [scrambled/](scrambled/), [docs/CLI.md](docs/CLI.md) |
| 10 Quantum-native 2 | Workflow notebook, incl. a Î¸zz sweep of where scrambling switches on | [notebook/](notebook/) |
| 11 FQxI | "Why you can't unscramble an egg (quantum edition)" explainer | [edu/](edu/) |

## Engines used

`otoc-echo-v1` Â· `blur-v1` Â· `telablur-v1` Â· `qrc-midi-v1` Â· `blur-midi-v1` Â· `blur-core-v1` Â· `entanglement-shader-v1` Â· `tamagotchi-v1` Â· `qpixl-v1` Â· `qdrive-api-v1`

Each has completed jobs whose output is used; [core/ENGINES.md](core/ENGINES.md) is generated from the job cache and lists them all. `retrocausal-echo-v1`, `tessa-image-v1`, `tomography-api-v2` and `deep-fryer-v1` were attempted and did not complete during the hack (server-side timeouts); they are not credited.

## Run it

```powershell
python -m venv .venv
.venv\Scripts\pip install -e ".[test,core]"
.venv\Scripts\pytest -q core tests            # 40+ tests
.venv\Scripts\scrambled --help
.venv\Scripts\scrambled replay --video        # rebuilds the demos from cache/, no key, no network
```

Every Atlas job is cached by content hash under `cache/`, so the whole project replays offline. To run live, put `MOTH_API_KEY=...` in `.env` and use `--mode atlas`. Web app: see [web/README.md](web/README.md). Plugin build: [plugin/README.md](plugin/README.md).

## Honesty notes

- All quantum runs are on the Aer emulator through Atlas, not quantum hardware.
- Echo audio is rendered locally from the measured tap maps (classical step) because `retrocausal-echo-v1` timed out on every job.
- Generative AI: Cursor agents wrote most of the code and drafted the docs under my direction. No generative image, audio or video models were used for the media. The photos and cooking footage are mine.

## Licence

MIT, see [LICENSE](LICENSE).
