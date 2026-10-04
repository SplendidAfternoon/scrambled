# SCRAMBLED workflow notebook

`scrambled_workflow.ipynb` is the whole SCRAMBLED pipeline on the Moth Atlas API, as one executed notebook that reads
top to bottom:

1. the OTOC F(i, t) and what it means
2. Atlas API anatomy: live engine schemas, the raw upload, process, poll and result lifecycle (presigned URLs
   redacted), caching and cost
3. `otoc-echo-v1`: the scrambling run and the Clifford control
4. an independent classical statevector check (matches Atlas to about 1e-13)
5. a theta_zz sweep over 10 Atlas runs (7 of them new) with a scrambling phase-diagram figure (`out/theta_zz_sweep.png`)
6. F to image: `blur-v1` / `telablur-v1` ladders and the per-qubit strip mapping
7. F to audio: the measured taps as an echo (local renderer, labelled classical), plus a recorded
   `retrocausal-echo-v1` attempt
8. F to video: `scrambled.video` on an 8 s excerpt (2 keyframes, 12 ladder jobs)
9. `tomography-api-v2` on the same echo circuit. The engine timed out server-side on every attempt, so the notebook
   shows the classical prediction and lists the failed job ids.
10. reproducibility, what is quantum and what is classical, credits, and a job id table

The committed notebook and `scrambled_workflow.html` come from a run with no API key (replay mode). Every Atlas
number in them comes from cached job records in `../cache/`.

## Run it

From the repo root, with the package installed (`.venv\Scripts\python -m pip install -e ".[test]"`), Jupyter in the
venv (`.venv\Scripts\python -m pip install jupyter nbconvert matplotlib`), and `ffmpeg`/`ffprobe` on `PATH`
(needed for sections 6 to 8):

### Replay (default): no key, no network, no credits

```powershell
$env:MOTH_API_KEY = ""          # optional: proves no key is needed
.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace notebook\scrambled_workflow.ipynb
```

Or open it in Jupyter or VS Code and run all cells. `MODE` defaults to `replay`, so every Atlas result is read from
`cache/`. A missing cache entry raises `ReplayMiss` instead of quietly computing something else.

### Atlas: live API

Put `MOTH_API_KEY=...` in `.env` at the repo root (the key is never printed), then:

```powershell
$env:SCRAMBLED_MODE = "atlas"
.venv\Scripts\jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=1800 notebook\scrambled_workflow.ipynb
```

Identical calls are cache hits and cost nothing. On a fully cached repo, an atlas run only submits one
`tomography-api-v2` attempt (1 credit) and resumes the pending `retrocausal-echo-v1` job if it has not finished yet.
The raw-HTTP demo in section 2.2 runs once and is then shown from `data/raw_api_transcript.json`. Set
`RAW_API_FORCE=1` to run it again (1 credit).

### Export HTML

```powershell
.venv\Scripts\jupyter nbconvert --to html notebook\scrambled_workflow.ipynb
```

### Regenerate the notebook source

The cells are defined in `build_notebook.py`, which keeps the notebook easy to diff:

```powershell
.venv\Scripts\python notebook\build_notebook.py   # rewrites scrambled_workflow.ipynb without outputs
```

## Files

| path | what |
|---|---|
| `scrambled_workflow.ipynb` | the executed notebook |
| `scrambled_workflow.html` | static HTML export |
| `build_notebook.py` | cell sources |
| `data/engine_schemas.json` | engine schemas fetched live from `GET /engines/{id}` (shown in replay mode) |
| `data/raw_api_transcript.json` | the raw-HTTP lifecycle transcript (URLs redacted) |
| `data/job_ledger.json` | every Atlas job submitted for this notebook, with outcome and credits |
| `data/retrocausal_attempt.json`, `data/tomography_attempts.json` | attempts at the two unreliable engines |
| `data/raw_demo_input.png`, `data/stem_6s_mono.wav` | small deterministic inputs (same bytes give the same asset id, so replay hits the cache) |
| `out/` | full-size media: `theta_zz_sweep.png`, egg frames, `eggs_scrambling.mp4`, `eggs_excerpt_scrambled.mp4` (with sound), echo WAVs, GIF previews |

## Notes

* **Emulator.** All OTOC data is from Atlas `otoc-echo-v1` with `machine: aer, exact: true`, an exact, noiseless
  emulator. It is not quantum hardware.
* **Classical steps** are labelled in the notebook: the verification simulation, the dense sweep curve, strip
  compositing, video encoding, the echo audio (numpy) and the tomography prediction.
* **Video replay** re-extracts keyframes with the local ffmpeg. A different ffmpeg build can give different PNG bytes,
  and therefore a cache miss. In that case section 8 shows the saved preview instead.
