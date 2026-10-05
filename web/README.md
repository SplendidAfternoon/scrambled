# SCRAMBLED: web explorer

Live at [scrambled-mu.vercel.app](https://scrambled-mu.vercel.app).

| Page | What it is |
|---|---|
| `index.html` | Landing page with the physics and honesty notes. |
| `explorer.html` | **SCRAMBLED Explorer.** Set θx, θzz (snaps to π, the Clifford point) and chain length, then press **Measure on Atlas** to run `otoc-echo-v1` live. It draws the measured `F(site, t)` heatmap, the light cone, how much echo survives over time, and the egg photo scrambling one strip per qubit as you scrub t. With no key it uses the site's lent demo key (rate limited) or browses the runs measured ahead of time. |

Static site: `npm run build` writes `dist/`. Deployed to Vercel with project root `web/`, which also serves the proxy in `api/`.

## How it calls Atlas

The client is `src/lib/atlas.ts`. It makes the documented three calls with `Authorization: Bearer <key>`:

1. `POST /api/v1/engines/otoc-echo-v1/process` with `{"params": {n_sites, depth: 32, theta_x, theta_zz, machine: "aer", exact: true, include_taps: false}}` returns a `job_id`.
2. `GET /api/v1/jobs/{job_id}/status`, polled with backoff until `completed`, `failed` or `cancelled`.
3. `GET /api/v1/jobs/{job_id}/result`. The client reads `result.output.data.series.F_re/F_im` and `extras.light_cone` / `extras.kick_site` (`fromAtlasResult` in `src/lib/otoc.ts`).

**Key handling.** A pasted key is held in memory, and in `sessionStorage` only if you tick "remember for this tab". It is sent only in the `Authorization` header of those three calls. Nothing is embedded in the build.

**CORS.** `api.mothquantum.com` only admits `http://localhost:3000`, so `npm run dev` (port 3000, `--strictPort`) calls Atlas directly and every other origin goes through the same-origin proxy `./api/atlas/<path>`. Force a route with `?atlas=proxy` or `?atlas=direct`.

**Proxy (`api/atlas.ts`).** A Vercel function that forwards only `engines/otoc-echo-v1/process`, `jobs/<uuid>/status` and `jobs/<uuid>/result`, passing your own `Authorization` header through without logging it. `npm run dev` mounts the same handler through Vite middleware.

**Recorded live runs.** Two verified browser runs (direct: job `e4bc0ee8`, proxy: job `3d742c99`) ship in `public/data/live_recorded.json` and appear as a "A real live run" card, so a visitor without a key still sees a genuine browser-initiated measurement.

### Judge demo key (lent server key)

Active only when `ALLOW_SERVER_KEY=1` and `MOTH_API_KEY` are set on the server and the request carries no `Authorization` header:

- **Submit only, clamped.** Only `POST engines/otoc-echo-v1/process`, with the body rebuilt from a whitelist: `n_sites` 2–12, `depth` 1–32, `theta_x` 0–π, `theta_zz` (−π, π], `theta_z` 0–π, always `machine: "aer"`, `exact: true`, `include_taps: false`.
- **Signed job ids.** The submit response adds `job_token`, an HMAC-SHA256 of the job id (`PROXY_SECRET`). Lent-key status and result reads need it in `X-Job-Token`, so the proxy only reads jobs it created. The key never reaches the browser.
- **Rate limits.** `SERVER_KEY_PER_IP_HOURLY` (default 3) per IP per hour and `SERVER_KEY_DAILY_CAP` (default 60) per UTC day. Counters use Upstash Redis / Vercel KV when configured, otherwise in-memory per function instance (a cold start resets them).
- **Health.** `GET /api/atlas/health` returns `{proxy, server_key, remaining, limits, counter}`, never the key. The explorer reads it on load and labels the button "Measure on Atlas (demo key, N left)".

`api/atlas.test.ts` covers clamping, both rate limits, token signing and forgery, 403 on unsigned lent-key reads, BYOK pass-through, and that no response body contains the key.

Production env: `ALLOW_SERVER_KEY`, `MOTH_API_KEY`, `PROXY_SECRET`, `SERVER_KEY_DAILY_CAP`, `SERVER_KEY_PER_IP_HOURLY`. Set `ALLOW_SERVER_KEY=0` once the key is rotated.

## Engines and job ids

All on Atlas's `aer` emulator.

**`otoc-echo-v1`.** The cached mode covers 68 measured runs: a grid from `scripts/build_data.py` (n ∈ {8, 12}, θx ∈ {0.1 … 0.5}π, θzz ∈ {0.15, 0.25, 0.35, 0.5, 0.75, 1}π) plus 8 earlier clean-Floquet runs from the shared `cache/`. Every job id, parameter set and F array is in `public/data/grid.json`; the two headline runs (scrambling `8df5cfa2`, Clifford control `89c7f269`) are also in `featured.json`. Between grid points the explorer shows the nearest measured run and labels it "nearest".

**`blur-v1`** (photo A, `reach: 0`, strength 0.1…0.4) and **`telablur-v1`** (photo A → photo B, strength 0.02…0.98) make the image ladders the strips are drawn from. Job ids are in `public/data/ladder.json`, rendered by `pipeline/m1b_images.py`; `scripts/build_images.py` resizes them to 512 px.

**Egg sprites.** `scripts/build_sprites.py` sends classical crops of the two photos through `blur-v1` (`tessa-image-v1` was tried first and timed out on every job). `public/data/sprites.json` records each job; `egg_fresh` is the site icon.

## Honesty notes

- `F(site, t)` is computed on the `aer` emulator with exact expectation values, not on quantum hardware.
- The light cone is the engine's own `extras.light_cone`. The Clifford control (θzz = π) keeps F at ±1 because Clifford circuits map Paulis to single Pauli strings. The revival around t ≈ 13–16 in the 12-qubit chain is a finite-size effect.
- Classical steps: cutting the photo into strips, crossfading between Atlas images, the "cooked" accumulator (∫(1 − |F|) dt) and sprite cropping.

## Develop

```powershell
cd web
npm install
npm run dev          # http://localhost:3000 (the one origin Atlas's CORS admits)
$env:ALLOW_SERVER_KEY="1"; npm run dev   # with the lent demo key (reads MOTH_API_KEY from ../.env)
npm test             # vitest: physics helpers, Atlas client, proxy rules
npm run build        # tsc + vite -> dist/
node scripts/e2e.mjs               # headless Chromium: landing + explorer, desktop + mobile, screenshots/
node scripts/live_check.mjs        # one live measurement from the explorer (reads MOTH_API_KEY from ../.env)
```

Regenerate data from the repo root (cached in `cache/`, so re-running costs nothing):

```powershell
.venv\Scripts\python web\scripts\build_data.py
.venv\Scripts\python web\scripts\build_images.py
.venv\Scripts\python web\scripts\build_sprites.py
```

## Layout

```
web/
  index.html  explorer.html
  src/explorer.ts
  src/lib/      otoc.ts (F maths, parsing) · atlas.ts (client) · draw.ts (heatmap) · eggstrip.ts (photo strips) · data.ts
  api/atlas.ts  Vercel proxy: BYOK forwarder + opt-in lent demo key (+ atlas.test.ts)
  public/data/  grid.json featured.json ladder.json sprites.json live_recorded.json
  public/img/ladder/  public/sprites/
  scripts/      build_data.py build_images.py build_sprites.py e2e.mjs live_check.mjs proxy_check.ts sprite_src/
  screenshots/
```
