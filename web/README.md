# SCRAMBLED: web app and game

Two browser experiences built on quantum information scrambling measured with Moth Quantum's Atlas platform.

| Page | What it is |
|---|---|
| `index.html` | Landing page with the physics and honesty notes. |
| `explorer.html` | **SCRAMBLED Explorer** (Moth Hack form 08, "Make a web app"). Set θx, θzz (snaps to π, the Clifford point) and chain length, then press **Measure on Atlas** to run `otoc-echo-v1` live with your own key. It draws the measured `F(site, t)` heatmap, the light cone, how much echo survives over time, and the egg photo scrambling one strip per qubit as you scrub t. With no key it browses the runs measured ahead of time. |
| `game.html` | **Don't Scramble the Egg** (form 05, "Quantum game"). Five levels. Each one is a 12-qubit chain drawn as eggs in a pan. You pick a pan (a measured circuit), watch the scrambling front reach the golden eggs, and serve while their echo is still above the line. It has a title screen, three lives, win and lose states, synthesized sound, steam, screen shake and a best score. Touch and keyboard (space) both work. You can also measure your own pan live. |

Static site: `npm run build` writes `dist/`. All asset paths are relative (`base: "./"`), so it works under a GitHub Pages subpath. Deploying to Vercel (project root = `web/`) also gives you the optional proxy in `api/`.

## How it calls Atlas

The client is in `src/lib/atlas.ts`. It makes the documented three calls with `Authorization: Bearer <key>`:

1. `POST /api/v1/engines/otoc-echo-v1/process` with `{"params": {n_sites, depth: 32, theta_x, theta_zz, machine: "aer", exact: true, include_taps: false}}` returns a `job_id`.
2. `GET /api/v1/jobs/{job_id}/status`, polled with backoff until `completed`, `failed` or `cancelled`.
3. `GET /api/v1/jobs/{job_id}/result`. The client reads `result.output.data.series.F_re/F_im` (an n_sites × depth array) and `extras.light_cone` / `extras.kick_site` (see `fromAtlasResult` in `src/lib/otoc.ts`).

**Key handling.** The key you paste is held in memory. It goes into `sessionStorage` only if you tick "remember for this tab". It is sent only in the `Authorization` header of the three calls above. Nothing is embedded in the build, and the repo's `.env` is never read by the web app.

### CORS finding (checked 2026-10-04)

`api.mothquantum.com` answers preflight requests with `access-control-allow-origin` **only for `http://localhost:3000`**. Origins like `localhost:5173`, `127.0.0.1:3000`, `*.github.io`, `*.vercel.app` and `mothquantum.com` get no CORS headers. So:

- **Local, direct:** `npm run dev` serves on port 3000 (`--strictPort`), and the browser calls the API directly. Verified end to end from headless Chromium with `scripts/live_check.mjs`: submit, poll and result all completed, and the run was drawn in the explorer. Job `e4bc0ee8-6eb2-4b3b-9d17-70b61fce25a5` (θx 0.22π, θzz 0.3π, 12 qubits); screenshot `screenshots/explorer-live.png`.
- **Deployed, via proxy:** everywhere else the client calls the same-origin `./api/atlas/<path>`.
  - `api/atlas.ts` is a Vercel serverless function (`vercel.json` rewrites `/api/atlas/:path*` to it). It forwards only `engines/otoc-echo-v1/process`, `jobs/<uuid>/status` and `jobs/<uuid>/result`. It passes your own `Authorization` header through without logging or storing it. It can also lend the site's key to visitors who have none (off by default; see [Judge demo key](#judge-demo-key-lent-server-key)).
  - `npm run dev` mounts the same `api/atlas.ts` handler at `/api/atlas` (Vite middleware), and `npm run preview` uses a plain forwarder (bring-your-own-key only). Force a route with `?atlas=proxy` or `?atlas=direct`. The proxy route was verified the same way: job `3d742c99-9e47-4cd6-b1e1-baa6ce392b3c`, screenshot `screenshots/explorer-live-proxy.png`. The Vercel handler itself was run in-process against the real API with `npx vite-node scripts/proxy_check.ts <job_id>`: it forwarded a status read (200), blocked `/me` (403) and refused a request with no key (401).
- **Static host without the proxy (GitHub Pages):** the measured runs work fully. **Measure on Atlas** reports that no proxy is present.

**Recorded live run.** Both verified browser runs above are shipped in `public/data/live_recorded.json` (full F arrays, light cone, timestamps, route). The explorer shows the first one in a "A real live run" card at the top of the controls; one click loads it, tagged *recorded live*, with its job id and submission time. That way a visitor without a key still sees a genuine browser-initiated Atlas measurement, not only the pre-measured grid.

### Judge demo key (lent server key)

So judges can trigger a live Atlas call without their own key, `api/atlas.ts` has an opt-in mode. It is active only when `ALLOW_SERVER_KEY=1` **and** `MOTH_API_KEY` are set in the server environment and the request carries no `Authorization` header:

- **Submit only, clamped.** Only `POST engines/otoc-echo-v1/process`. The body is rebuilt from a whitelist: `n_sites` 2–12, `depth` 1–32, `theta_x` 0–π, `theta_zz` (−π, π], `theta_z` 0–π, and always `machine: "aer"`, `exact: true`, `include_taps: false`. Anything else (`shots`, `allow_high_shots`, other machines, QPU tokens, other engines) is dropped or refused.
- **Signed job ids.** The submit response adds `job_token`, an HMAC-SHA256 of the job id (secret `PROXY_SECRET`, or a hash derived from the key if unset). Lent-key `status`/`result` reads require that token in `X-Job-Token`, so the proxy only reads jobs it created. The response also carries the clamped `params` and the remaining quota. The key itself is never sent to the browser.
- **Rate limits.** Per IP: `SERVER_KEY_PER_IP_HOURLY` (default 3) submits per clock hour. Global: `SERVER_KEY_DAILY_CAP` (default 60) per UTC day. Refused requests don't use quota. Counters live in Upstash Redis / Vercel KV when `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN` (or `KV_REST_API_URL` + `KV_REST_API_TOKEN`) are set. **Otherwise they fall back to in-memory counters per function instance**: a cold start resets them and parallel instances each count separately, so the real ceiling is (cap × live instances). Configure KV if that matters.
- **Health.** `GET /api/atlas/health` returns `{proxy, server_key, remaining: {ip_hour, today}, limits, counter}` and never the key. The explorer calls it on load. If the key field is empty and `server_key` is true, the button reads "Measure on Atlas (demo key, N left)" and goes through the proxy. 16-qubit runs ask for your own key. Without the lent key, the explorer stays in cached mode plus the recorded live run.

Verified locally with `$env:ALLOW_SERVER_KEY="1"; npm run dev` and `LENT=1 TAG=-lent TX=0.26 TZZ=0.45 node scripts/live_check.mjs`. With the key field empty, the button read "demo key, 3 left". Job `11e0a7b0-5141-43e0-810e-c278f6d60396` completed on `aer` through `/api/atlas`, the status/result reads carried `X-Job-Token` and no `Authorization`, no response body contained the key, the quota then read 2 left, and an unsigned lent-key result read got 403. Screenshots: `screenshots/explorer-live-lent.png` and `screenshots/explorer-recorded.png`. On a real deploy the same check is open `/explorer.html` and press the button.

Tests: `api/atlas.test.ts` covers clamping, per-IP and daily limits (fake clock, Upstash pipeline format), token signing and forgery, 403 on unsigned lent-key reads, BYOK pass-through, and that no response body contains the key.

## Deploy to Vercel

Not deployed yet. These steps are for whoever deploys:

1. Import the repo in Vercel and set **Root Directory = `web`**. `vercel.json` sets `framework: vite`, `npm ci`, `npm run build`, output `dist`, the function `api/atlas.ts` (30 s max) and the `/api/atlas/:path*` rewrite. `.vercelignore` keeps test files out of `api/`.
2. Environment variables (Production):

   | name | required | meaning |
   |---|---|---|
   | `ALLOW_SERVER_KEY` | for the judge demo | `1` turns the lent key on. Anything else leaves BYOK only. |
   | `MOTH_API_KEY` | with the above | Atlas key used for lent runs. Server-side only, never returned. |
   | `PROXY_SECRET` | recommended | HMAC secret for job tokens (any long random string). |
   | `SERVER_KEY_DAILY_CAP` | optional | global lent runs per UTC day, default 60 |
   | `SERVER_KEY_PER_IP_HOURLY` | optional | lent runs per IP per hour, default 3 |
   | `UPSTASH_REDIS_REST_URL` / `UPSTASH_REDIS_REST_TOKEN` (or `KV_REST_API_URL` / `KV_REST_API_TOKEN`) | optional | shared counters; without them limits are per instance, in memory |

3. Deploy, then check `https://<site>/api/atlas/health` shows `"server_key": true`, open `/explorer.html` with the key field empty, and press **Measure on Atlas**.

CLI equivalent: `cd web && vercel link && vercel env add ALLOW_SERVER_KEY production` (repeat per variable) `&& vercel deploy --prod`.

## Engines and job ids

Everything below was produced on Atlas. The `aer` emulator was used throughout. No QPU.

**`otoc-echo-v1`** (12-qubit chain, depth 32, exact, kick Z on the centre qubit, clean Floquet). These back the explorer's cached mode and every game level:

| θx | θzz | game pan | job id |
|---|---|---|---|
| 0.3π | 0.35π | "High heat": scrambling (the video's headline run) | `8df5cfa2-e57c-43a8-a93a-63975efd252c` |
| 0.3π | π | "Clifford lid": control, no scrambling (as in the video) | `89c7f269-9a0c-473a-936d-a0ac2a08aa77` |
| 0.3π | 0.25π | "Sparse stir": scrambling, then a finite-size revival | `3d2ec1e7-7ef5-4ff2-a8e6-253c3b4719c5` |
| 0.1π | 0.35π | "Low heat": weak drive, slow spreading | `6865b18c-cf62-4f31-a002-98f36c236bf3` |

The explorer's cached mode covers **68 measured runs**. 60 come from the grid in `scripts/build_data.py`: n ∈ {8, 12}, θx ∈ {0.1, 0.2, 0.3, 0.4, 0.5}π, θzz ∈ {0.15, 0.25, 0.35, 0.5, 0.75, 1}π. The other 8 are earlier clean-Floquet runs with depth 32 and the default kick, taken from the repo's shared `cache/`: θzz = 0 and 0.6–0.95π, plus one 10-site and one 16-site chain. All 68 go through the cached client `moth.run`. Every job id, parameter set and F array is in `public/data/grid.json`; the two headline runs are also in `featured.json`. When the sliders sit between grid points, the explorer shows the nearest measured run and labels it "nearest".

**`blur-v1`** (photo A, `reach: 0`, strength 0.1…0.4) and **`telablur-v1`** (photo A → photo B, strength 0.02…0.98). These are the image ladders the explorer's strips are drawn from. Job ids are in `public/data/ladder.json`, rendered earlier by `m1b_images.py`. `scripts/build_images.py` resizes them to 512 px.

**Game sprites: `blur-v1`, with `tessa-image-v1` planned first.** `scripts/build_sprites.py` crops one whole egg from photo A and a patch of scrambled egg from photo B (classical crop and mask, kept in `scripts/sprite_src/`). It sends each crop through an Atlas image engine.

- **Tessa first.** The plan is Tessa's quantum colour-sphere round trip, with different shot counts and one IBM-calibrated noisy emulator as the "cooking" states: 4096 shots = fresh, 256 = cracked, 48 = cooking, `fake_torino` = burnt. Tessa's `distortion` gate is rejected on emulators (`distortion_without_hardware`), so it is not used.
- **Blur fallback.** On 2026-10-04 every `tessa-image-v1` job failed with `engine_timeout`, including a 32 px probe (job `4a42a6fd-bc5d-4897-ad5d-be33bbd173ea`). A retry at 05:03 local (21:03 UTC) failed the same way (job `d955894d-4386-4437-a9ef-931639678d48`, `engine_timeout`). The script therefore made the shipped sprites with `blur-v1` at rising strength: fresh 0.05, cracked 0.25, cooking 0.45, burnt 0.6 (reach 0.2), scrambled 0.08, scrambled-hot 0.35 (reach 0.3). The sprite's alpha acts as the blur mask.

`public/data/sprites.json` records the job id, engine and params for every sprite, plus the Tessa failure it fell back from. Re-run the script when Tessa is back: it tries Tessa first, the cache keeps the blur results, and the game's credits line reads the engine names from `sprites.json`. The game's last resort is the plain crops in `public/sprites/src/`.

| sprite | blur-v1 job id |
|---|---|
| egg_fresh | `d1b4ceed-4d10-435f-83fb-3dce5328d20e` |
| egg_crack | `ce597fa6-7b5e-415d-8e46-c44e9528b7cc` |
| egg_cook | `650135dc-d413-48fb-83e8-881443423272` |
| egg_burnt | `5a31568b-1db6-4108-b3fb-fddd1932d105` |
| egg_scrambled | `04d6c2d1-f18e-4e27-8b7b-2b102f2c1d59` |
| egg_scrambled_hot | `56710a36-de2f-4772-8a67-2a0168a0cb55` |

## Honesty notes

- `F(site, t)` is the out-of-time-order correlator that `otoc-echo-v1` measures: forward evolution U, a Z kick on the centre qubit, then U†. It is computed on the `aer` emulator with exact expectation values, not on quantum hardware.
- The **light cone** is the engine's own `extras.light_cone`. The **Clifford control** (θzz = π) keeps F at ±1 because Clifford circuits map Paulis to single Pauli strings. The revival around t ≈ 13–16 in the 12-qubit chain is a finite-size effect: the front reflects off the chain ends.
- **Classical steps:** cutting the photo into strips, crossfading between Atlas images, the "cooked" accumulator (∫(1 − |F|) dt, the same mapping as the video's `compose.py`), sprite cropping, all game logic, and all sound (synthesized with WebAudio). The game judges your serve on the measured |F| at the golden eggs, interpolated linearly between integer echo steps.
- Level windows are checked against the shipped data in `src/game/levels.test.ts`. Every level is winnable, and on choice levels the pan you pick matters.

## Develop

```powershell
cd web
npm install
npm run dev          # http://localhost:3000 (the one origin Atlas's CORS admits)
$env:ALLOW_SERVER_KEY="1"; npm run dev   # same, with the lent demo key (reads MOTH_API_KEY from ../.env, in-memory limits)
npm test             # vitest: physics helpers, Atlas client, proxy rules, game rules, level solvability
npm run build        # tsc + vite -> dist/
node scripts/e2e.mjs               # headless Chromium: explorer + full game playthrough, desktop + mobile, screenshots/
node scripts/live_check.mjs        # one live measurement from the explorer (reads MOTH_API_KEY from ../.env)
```

Regenerate data from the repo root with the Python venv. Results are cached in `cache/`, so re-running costs nothing:

```powershell
.venv\Scripts\python web\scripts\build_data.py
.venv\Scripts\python web\scripts\build_images.py
.venv\Scripts\python web\scripts\build_sprites.py
```

## Layout

```
web/
  index.html  explorer.html  game.html
  src/lib/      otoc.ts (F maths, parsing) · atlas.ts (client) · draw.ts (heatmap) · eggstrip.ts (photo strips) · data.ts
  src/game/     rules.ts (judge, lives) · levels.ts · runs.ts · audio.ts · main.ts · game.css
  api/atlas.ts  Vercel proxy: BYOK forwarder + opt-in lent demo key (+ atlas.test.ts)
  vercel.json  .vercelignore
  public/data/  grid.json featured.json ladder.json sprites.json live_recorded.json
  public/img/ladder/  public/sprites/
  scripts/      build_data.py build_images.py build_sprites.py e2e.mjs live_check.mjs proxy_check.ts sprite_src/
  screenshots/
```
