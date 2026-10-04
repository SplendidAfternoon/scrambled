# SCRAMBLED / The Quantum Egg (Form 03, "Three dimensions")

A procedural 3D egg whose shell material comes from **entanglement-shader-v1**, and which cracks open according to the **measured** quantum scrambling of a 12-qubit chain (**otoc-echo-v1**). The interior, revealed through the cracks, is the egg mesh itself passed through **blur-core-v1** (mesh → JSON grid → engine → JSON grid → mesh).

- Video: `out/quantum_egg.mp4`: 1080×1080, 30 fps, 45 s, H.264 + AAC stereo 48 kHz (256 kb/s), mastered to −15.9 LUFS integrated, true peak −1.8 dBTP
- Silent picture-only copy: `out/quantum_egg_silent.mp4`
- Contact sheet: `out/quantum_egg_contact.jpg`
- Preview stills: `out/stills/`

## Pipeline

```
probes/otoc_scrambling.json ─┐   (otoc-echo-v1, measured earlier, F(site,t) 12×32)
probes/otoc_control_clifford ┤
                             │
egg_mesh.py ── procedural egg (Hügelschäffer profile, 128×128 = 16 384 verts)
   │            └─ radius grid r[θ,φ] ──► blur-core-v1 (zero-blur round trip first, then a strength/reach ladder)
   │                                       └─► engine_outputs/blurcore_*.json, meshes/*.obj
   │
entanglement-shader-v1 ──► engine_outputs/9214cb9d_…zip ──► shader_9214cb9d/ (GLSL, OSL, HLSL, MaterialX, R/T LUTs)
   │
prep_data.py ── decodes R_lut.hdr / T_lut.hdr, packs F(site,t), blur grids, crack seeds ──► web/scene_data.js
   │
web/main.js ─── three.js scene (custom ShaderMaterials), deterministic renderAt(time)
render.mjs ──── headless Chromium (Playwright, Edge channel, GPU via ANGLE/D3D11) → PNG frames → ffmpeg → mp4
contact_sheet.py ─ 4×4 frame grid from the finished video
```

### 1. The shell: entanglement-shader-v1, used as intended

The engine returns a ZIP of shader formats plus two float lookup tables, `R_lut` (reflectance) and `T_lut` (transmittance), indexed by incident angle θ (rows, 0…π/2) and interference phase (columns, periodic). The shell's fragment shader is the engine's own `entanglement_texture.glsl` maths, kept as is: `cosθ = |N·V|`, `D = −4π·thickness·cosθ`, per-channel phase `s = mod(D/λ, 2π)/2π` with λ = 650/530/470 nm, and `t = θ/(π/2)`. It samples both LUTs with the sampler settings the engine specifies (REPEAT on phase, CLAMP on angle, no vertical flip). Then it combines them the way the engine's OSL BSDF does, `Reflectance × specular + Transmittance × transparent`:

- `R` tints the reflection of a procedural studio environment (key softbox, cool rim, warm fill), and also tints a faint cream eggshell base so the shell still reads as an egg.
- `T` sets the shell's opacity (the opacity is held at 0.72 or above so the cracks stay readable).
- The one change we made: the stack thickness (default 500 nm) is multiplied by `1 + 0.22·(1 − Re F)` for each latitude band. This means the measured sign flips of Re F show up as colour shifts on the shell.

Engine parameters: `reflectance 0.3, absorption 0.6, layers 3, incoming_rays 8, interaction 1.0, style "frustrated", resolution 128`. The LUTs are 128×128, R ∈ [0.19, 1.55] (HDR) and T ∈ [0, 0.67].

### 2. The cracks: measured scrambling F(site, t)

- The 12 chain sites map to 12 **latitude bands**. Site 0 is the pointy pole, site 11 the blunt pole, and the kick site (site 6) sits just below the equator. Values are interpolated linearly between band centres.
- Echo steps t = 1…32 play over 24 s (0.75 s per step), with smoothstep interpolation between steps. t = 0 means before the kick, where F = 1.
- Scrambling per band is `s = 1 − |F(site,t)|`. It drives three things:
  - **Crack grooves and gaps.** The shell is split into 90 Voronoi fragments (same seeds as the crack relief sent to blur-core). As `s` rises, cracks open along fragment edges and glow at the rim.
  - **Fragments lifting off.** Each fragment moves rigidly outward once `s` at its seed's latitude passes a per-fragment threshold. During the finite-size revival (|F| rises again around t ≈ 13–16) some fragments drift back, because the data does.
  - **Interior morph.** The interior steps through the blur-core ladder as the band-averaged `s` rises.
- **Control.** In the control run, θzz = π makes the circuit Clifford, and the measured |F| = 1 at every site and step. Fed through the same mapping, it gives s = 0 everywhere, so the egg stays whole (shown at 37–41 s with its own heatmap).
- A HUD heatmap shows the measured |F(site, t)| grid revealed up to the current step.

### 3. The interior: blur-core-v1 on the egg mesh

The egg is stored as a 128×128 grid of radii `r[θ_i, φ_j]` measured along fixed unit directions from the egg centre. That grid is exactly the rectangular, non-negative `values` array blur-core-v1 accepts: 2¹⁴ points, so 14 qubits. Reading the OBJ back gives the radii; writing the returned radii along the same directions with the same faces gives a new OBJ.

- **Zero-blur round trip first** (Moth's tip from the Discord thread): `strength 0` gives a max abs error of 5.0e-7 on radii of about 0.5. That is the 6-decimal rounding of the JSON payload, so the obj ↔ JSON path is lossless. The script refuses to continue if this error exceeds 1e-4.
- The engine rescales its output relative to the input's maximum. We undo that (`out × max(in)/max(out)`). In the render, each blurred grid is also shrunk uniformly so that it fits inside the shell.
- Ladder input: the egg with a 6 % deep Voronoi crack relief. Visible results range from fine ripples at low strength to strong terraced banding at `reach 0.5–1.0`. The banding is the engine's Gray-coded qubit structure showing through.

| label | params | job id | mean abs change in radius |
|---|---|---|---|
| s0_roundtrip (plain egg) | strength 0 | `a3d7591d-b965-46c7-be99-f005a3ca32a1` | 5e-7 max |
| crack_s000 | strength 0 | `61381c79-8679-40a7-9d41-a56c43cc5867` | 4e-7 |
| crack_s015 | strength 0.15 | `408871e7-f614-492b-80a6-7a38da1f7ce8` | 0.0010 |
| crack_s035 | strength 0.35 | `4382a7a5-3049-48e4-b4d6-6d4690cb9028` | 0.0039 |
| crack_s060 | strength 0.6 | `ded774e0-d3b3-404c-bca7-7f59b533498e` | 0.0066 |
| crack_s060_r05 | strength 0.6, reach 0.5 | `3b5de2a4-190d-4b85-8e01-4f9076d0def1` | 0.038 |
| crack_s090_r10 | strength 0.9, reach 1.0 | `dfffd89c-d836-4347-a054-5616946eded7` | 0.084 |

The interior morph uses crack_s000 → s035 → s060 → s060_r05 → s090_r10. All meshes are in `meshes/` (OBJ) and the raw engine results are in `engine_outputs/blurcore_*.json`.

### 4. Sound: built from the same measurement (`sound_bed.py`)

All of the sound processing is classical. It is designed from measured data, and no engine runs at audio time.

- **Bed.** The project's cooking audio (`../media/stem_full.wav`) is rendered through the measured otoc-echo-v1 tap map with `../audio_local.render`, a classical multi-tap render of measured taps. Each tap becomes one echo: depth sets the delay, |F| the level, site the pan, and negative polarity inverts the echo.
  - The **scrambling** render plays from 8 s to 37 s. Its gain follows the measured band-mean 1−|F|, using the same interpolation as the picture.
  - The dry stem plays under the title and intro.
  - The **Clifford control** render (|F| = 1, so every echo is a clean, in-phase copy) plays at a low level under 37–41 s.
- **Crack events.** Each latitude band (site) gets one short crack sound at the moment its 1−|F| first crosses the shell's crack threshold. That threshold is `s > 0.12/1.3 ≈ 0.092`, the same value the shader uses to open cracks. The crack is a filtered click plus a damped ping, panned by site, with higher pitch toward the pointy pole. These 12 cracks fall between 8.1 s and 12.7 s and follow the light cone outward from site 6.
- **Fragment events.**
  - A soft low thunk plays whenever a band's 1−|F| rises through the fragment-lift level `0.78/1.3 = 0.6` (the lowest lift onset in the shader). There are 38 of these.
  - A quiet glassy "settle" ping plays whenever it falls back below that level (29 of these). Most of those cluster at the finite-size revival.
- **Control.** The Clifford data produces **0** threshold crossings, so the control section carries only the clean echo bed. It measures −22.3 LUFS, against about −14 to −15 LUFS in the scrambling section.
- **Event list.** Every event, with its time, site and type, is in `audio/events.json`.
- **Mastering.** Two-pass ffmpeg `loudnorm` (I −16, linear), then a limiter at −2 dBFS, then AAC encoding. Verified on the final mp4 with `ebur128=peak=true`: integrated **−15.9 LUFS**, LRA 9.2 LU, true peak **−1.8 dBTP**.

| section | 0–8 s intro | 8–20 s light cone | 20–32 s scrambled | 32–37 s inside | 37–41 s Clifford control | 41–45 s end |
|---|---|---|---|---|---|---|
| loudness (LUFS, per section) | −16.8 | −14.1 | −15.4 | −18.9 | −22.3 | −24.9 |

## Job ids (all Moth Atlas)

| engine | job id | notes |
|---|---|---|
| entanglement-shader-v1 | `9214cb9d-e1ab-413d-80c1-2bd4c00c2f20` | took 713 s (queue + processing); output ZIP is in `engine_outputs/` |
| blur-core-v1 | 7 jobs, listed above | 128×128 grids, exact (no shots) |
| otoc-echo-v1 | `8df5cfa2-e57c-43a8-a93a-63975efd252c` (scrambling) | run earlier in the project; see `../probes/` |
| otoc-echo-v1 | `89c7f269-9a0c-473a-936d-a0ac2a08aa77` (control) | θzz = π (Clifford); `../probes/otoc_control_clifford.json` |

All engine calls go through `../moth.py` (content-addressed cache in `../cache/`). Re-running `egg_mesh.py` uses the cache and costs no credits.

## Reproduce

```powershell
cd three
npm install                                   # three + playwright (uses the installed Edge; set PW_CHANNEL=chromium for bundled Chromium)
..\.venv\Scripts\python egg_mesh.py           # blur-core runs (cached), writes meshes + engine_outputs
..\.venv\Scripts\python prep_data.py          # → web/scene_data.js
node render.mjs --stills 6,19,28              # quick look → out/stills/
node render.mjs                               # 1350 frames → out/quantum_egg.mp4 (~5 min on a Radeon 780M)
..\.venv\Scripts\python sound_bed.py          # sound bed → audio/, keeps the silent render as out/quantum_egg_silent.mp4, muxes audio into out/quantum_egg.mp4
..\.venv\Scripts\python contact_sheet.py out/quantum_egg.mp4 out/quantum_egg_contact.jpg
```

After a fresh `node render.mjs`, delete `out/quantum_egg_silent.mp4` before running `sound_bed.py`. Otherwise it muxes onto the old silent copy.

The entanglement-shader ZIP is already in `engine_outputs/`. To regenerate it, call `moth.run('entanglement-shader-v1', {...params above...})`, then `moth.fetch_outputs`, then unzip into `engine_outputs/shader_<job8>/`.

## Honesty notes

- **Emulator.** Every quantum step ran on Moth Atlas engines on the emulator. The OTOC data is `machine: aer, exact: true`. No QPU was used.
- **What is quantum-derived.** The R/T tables (entanglement-shader-v1), the blurred radius grids (blur-core-v1) and F(site, t) (otoc-echo-v1). Each is used as returned by its engine, apart from the rescaling and fitting described above.
- **What is classical.** The egg mesh, the Voronoi crack pattern, the mapping from F to latitude bands and from scrambling to cracks, fragments and morph weights, the studio lighting, the yolk shading, the camera, the captions and the rendering (three.js in headless Chromium, encoded with ffmpeg). The whole sound bed is classical too: a local multi-tap render of the measured taps, crack and fragment sounds synthesised at measured threshold crossings, and the mastering. These are artistic choices, not physics.
- **Physics wording.** F(site, t) is the out-of-time-order correlator after a Z kick at site 6. |F| < 1 means the kick has reached that site, so the cracks trace the light cone. Late |F| ≈ 0.3 means the information is spread across the chain, not lost. The partial rise around t ≈ 13–16 is a finite-size revival of a 12-site chain. The Clifford control (θzz = π) does not scramble: |F| = 1 everywhere.
- **Visual choices.** Fragment flight distance, crack width and the shell opacity floor were chosen for readability. They do not encode extra data.
