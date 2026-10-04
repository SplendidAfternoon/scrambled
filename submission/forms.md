# SCRAMBLED: submission texts (draft v1)

Shared fields (all 11 forms)
- Team or individual: Individual
- Name: Mana Blumicz
- Email: manablumicz@gmail.com
- Discord: katakaigo
- GitHub: SplendidAfternoon
- Occupation: TODO (Mana to confirm)
- QPU or emulation: Emulation (Qiskit Aer through Moth Atlas)
- Code repository: https://github.com/SplendidAfternoon/scrambled
- Demo URL: TODO (Vercel link)
- Generative AI: Yes. Cursor agents (Claude) wrote most of the code and drafted the docs under my direction; I chose the physics, the egg concept, the shots and the edits, and checked every claim against the measured data. No generative image, audio or video models were used for the media.
- Non-Moth APIs: none for the media. Vercel hosts the web app.

---

## 01 One image, one engine

**Title:** SCRAMBLED: One Egg, One Engine

**Elevator pitch:** A photo of whole eggs run once through Moth's quantum blur, with the blur strength set by how much information a 12-qubit chain loses when it scrambles.

**Project description (TODO count, 100–200):**
I photographed four eggs in a pan and ran that single image once through blur-v1. The parameters come from a measurement: on Moth Atlas I ran otoc-echo-v1, which nudges one qubit in a chain of twelve, runs the circuit forward and backward, and checks how much of the nudge comes back. In the scrambling setting only about a quarter of it does, so I set the blur strength from what was lost. The image shows the eggs at the moment their information has spread across the pan, still all there but no longer readable from any one place. It is the first frame of a larger project called SCRAMBLED, in which the same measurement drives a film, a track, a game, a plugin and a 3D egg.

**Technical description (50–100):**
Input: one 1024×1024 crop of a phone photo. Engine: blur-v1, one job (id in params.json). Strength and reach were chosen from the late-time mean |F| of an otoc-echo-v1 run (12 sites, depth 32, theta_x 0.3π, theta_zz 0.35π, Aer emulator, exact). Full parameter set, including defaults, is attached and in the repo under hero/.

---

## 02 Make it audible

**Title:** SCRAMBLED: the track

**Elevator pitch:** An 88-second track in which the sound of eggs cooking is echoed through a measured quantum scrambling map, so you can hear an echo come back whole, fade, invert and return.

**Project description:**
I recorded the sound of eggs scrambling in a pan and used it as the raw material for a piece about quantum information scrambling. On Moth Atlas, otoc-echo-v1 measures how a small nudge to one qubit spreads through a chain of twelve. Each measured value becomes an echo tap, with its delay set by the circuit step, its level by how much of the nudge survives and its polarity by the sign of the echo. The track has three acts. In the first the circuit cannot scramble, so every echo returns intact; in the second a gentle drive lets the echoes thin out slowly; in the third they spread, cancel and partly come back around step fifteen, when the disturbance reflects off the ends of the chain. A melody derived from the cooking audio was re-sequenced with qrc-midi-v1 and blurred per act with blur-midi-v1, with the blur set by each act's measurement.

**Technical description:**
Engines: otoc-echo-v1 (scrambling maps), qrc-midi-v1 and blur-midi-v1 (melody). Echo taps are rendered locally from the measured map, a classical step I label as such, because retrocausal-echo-v1 timed out on every job during the hack. The mix adds a classical FM synth and a drone, mastered to −14 LUFS. The workflow summary, the tap mapping and every job id are in core/README.md and measurements/MEASUREMENTS.md.

---

## 03 Three dimensions

**Title:** SCRAMBLED: The Quantum Egg

**Elevator pitch:** A 3D egg whose iridescent shell comes from Moth's Entanglement Shader and which cracks open band by band as a measured quantum scramble spreads through it.

**Project description:**
The Quantum Egg is a 45-second render of a procedural egg. Its shell uses the Entanglement Shader, Moth's quantum-computed thin-film material, so the iridescence itself comes from Atlas. The cracking is driven by a measurement: twelve latitude bands on the shell stand for the twelve qubits in an otoc-echo-v1 run, and each band cracks as its share of the original nudge drains away. Fragments lift off as the scramble spreads and drift partly back during the finite-size revival around step fifteen, which is in the data and which I wanted visible. The interior is the egg mesh itself run through blur-core-v1. A control run, in which the circuit cannot scramble, leaves the egg whole, so the difference you see is the difference the physics makes.

**Technical description:**
Engines: entanglement-shader-v1 (shell BSDF, GLSL from the returned ZIP, R/T tables drive reflection and opacity), otoc-echo-v1 (crack timing from 1−|F(site,t)|), blur-core-v1 (interior mesh, 7 jobs, zero-blur round trip checked to 5e−7). Rendered with three.js in headless Edge at 1080×1080, 30 fps, with a sound bed from the same measurement. The pipeline, every job id and the reproduction steps are in three/README.md.

---

## 04 Moving image

**Title:** SCRAMBLED

**Elevator pitch:** An 88-second film in which a pan of whole eggs turns into scrambled eggs strip by strip, following a quantum scramble measured on Moth Atlas.

**Project description:**
SCRAMBLED is about why you cannot unscramble an egg, told with a quantum measurement. On Moth Atlas I nudged one qubit in a chain of twelve, ran the circuit forward and backward, and measured how much of the nudge came back at each qubit and step. The film splits a shot of eggs into twelve vertical strips, one per qubit. When a qubit still holds the nudge its strip stays whole; as the information spreads, the strip passes through Moth's quantum blur and then morphs, through telablur, into a photo of the same pan after scrambling. The first act uses a circuit that cannot scramble, so only the nudged strip changes. The second and third acts scramble slowly and then quickly, and around step fifteen part of the egg briefly returns, which is the chain's finite size showing up on screen. A heatmap of the live data runs under each act.

**Technical description:**
Engines: otoc-echo-v1 (three measured maps, 12 sites, depth 32, Aer exact), blur-v1 and telablur-v1 (image ladders, square inputs), qrc-midi-v1 and blur-midi-v1 (score). Compositing in Python and ffmpeg, labelled classical. An independent numpy statevector reproduces every Atlas map to 7e−14, which confirms the circuit. The code, every job id and the steps to rebuild the film offline are in the repo.

---

## 05 Quantum game

**Title:** Don't Scramble the Egg

**Elevator pitch:** A five-level browser game where you cook a row of quantum eggs and have to serve before the measured scramble reaches the golden one.

**Project description:**
Each level of Don't Scramble the Egg is a real otoc-echo-v1 measurement from Moth Atlas. Twelve eggs in a pan stand for twelve qubits, one egg gets the nudge, and as you cook, the measured scramble spreads outward one neighbour per step, so the golden egg's echo fades on the timeline that the circuit actually produced. You choose a pan (a circuit setting) and decide when to serve: too early and the eggs are raw, too late and the golden egg is lost, and the revival around step fifteen gives a second chance if you know to wait for it. Later levels use different couplings, including the Clifford setting where nothing scrambles at all. If you have an Atlas key you can measure your own pan in the browser and play it.

**Technical description:**
Vite and TypeScript, static site on Vercel. Levels are built from cached otoc-echo-v1 runs (job ids shipped with the data); a live mode calls the Atlas API through a small allowlisted proxy. Sprites are egg photos processed with blur-v1. WebAudio for sizzle and echo pings. 39 unit tests, full playthrough tested in headless Chromium on desktop and mobile.

---

## 06 Daisy Chain

**Title:** SCRAMBLED: one measurement, many engines

**Elevator pitch:** One quantum measurement of information scrambling, passed through TODO Moth engines to become a film, a track, a 3D egg, a game, a plugin and an explainer.

**Project description:**
SCRAMBLED starts from one physical question, how fast a nudge to one qubit spreads through a chain of twelve, and passes the answer through every Atlas engine where it had a real job to do. otoc-echo-v1 makes the measurement. blur-v1 and telablur-v1 turn it into images, taking a pan of eggs from whole to scrambled strip by strip. qrc-midi-v1 re-sequences a melody from the cooking audio and blur-midi-v1 blurs it by the measured amount. entanglement-shader-v1 gives the 3D egg its shell and blur-core-v1 cracks its interior. TODO extra engines. Each engine's output feeds a finished piece, and the repo lists every job id next to the file it produced, so each use can be checked.

**Technical description:**
TODO engines with completed jobs, about 200 job ids in total, all listed in core/ENGINES.md, which is generated from the job cache. Everything runs on the Aer emulator through the Atlas API. A Python client caches every job, so the whole project replays offline without a key. retrocausal-echo-v1 was attempted and timed out server-side.

---

## 07 Make a VST or AU

**Title:** Scrambled Echo

**Elevator pitch:** A VST3 delay whose taps are measured quantum scrambling maps from Moth Atlas, so the echoes spread, fade and flip sign the way information does in a 12-qubit chain.

**Project description:**
Scrambled Echo is a delay plugin built from otoc-echo-v1 measurements. Each map is a grid of twelve qubits by thirty-two steps; every cell becomes a tap, with the step setting its delay, the surviving echo its gain, the sign its polarity and the qubit its stereo position. The Scramble knob blends from a Clifford map, where nothing scrambles and only one echo flips, into a fully scrambled one, and a second view plays the squared commutator so the light cone itself becomes audible. Two maps were measured with the nudge off-centre, which makes the echoes sweep across the stereo field. Nine measured presets ship with the plugin, and you can load your own map from an Atlas run. The audio examples include the cooking sound from the rest of the project.

**Technical description:**
VST3 for Windows x64, built with DPF and zig's clang. Nine otoc-echo-v1 maps are embedded (job ids in the README); custom maps load as JSON. Controls: Map, Scramble, View, Time or tempo sync, Mix, Feedback, Width. DSP core has 50 unit tests; impulse responses match the measured data to 2e−7 in a host. Five dry and wet audio examples were rendered through the binary.

---

## 08 Make a web app

**Title:** SCRAMBLED Explorer

**Elevator pitch:** A web app where you set two circuit dials, measure a 12-qubit scramble on Moth Atlas, and watch a pan of eggs scramble according to the result.

**Project description:**
The Explorer lets anyone see information scrambling happen. Two sliders set the circuit: the strength of the kick and the coupling between neighbours, which snaps to the Clifford point where nothing can scramble. Pressing Measure on Atlas sends an otoc-echo-v1 job to Moth's API and draws the result as a heatmap with the light cone marked, a curve of how much of the nudge survives, and a photo of eggs that scrambles strip by strip as you play it back. Without a key, the app browses 68 runs I measured in advance and labels the nearest one, so nothing is simulated in the browser. A rate-limited judge mode lets visitors run a real measurement without their own key.

**Technical description:**
Vite and TypeScript on Vercel. The browser submits, polls and fetches otoc-echo-v1 jobs through a serverless proxy (Atlas only allows CORS from localhost), which forwards the visitor's key or, in judge mode, a server key clamped to cheap emulator runs with a rate limit. Image ladders from blur-v1 and telablur-v1. 39 unit tests plus end-to-end checks.

---

## 09 Quantum-native 1

**Title:** scrambled: a quantum scrambling engine for media

**Elevator pitch:** An open-source Python tool that measures quantum information scrambling on Moth Atlas and uses it to scramble any image, sound or video.

**Project description:**
scrambled is the engine behind the rest of the project, packaged so anyone can use it. You give it a photo, a sound or a video, and it measures an out-of-time-order correlator on Moth Atlas, then uses the measured map to process the media: twelve strips of a frame each follow one qubit through Moth's blur and telablur engines, and audio is echoed through the measured taps. The demos are my 58-second cooking video, scrambled, and a Game of Life clip, which shows the tool working on material that has nothing to do with eggs. A classical statevector simulator inside the package reproduces the Atlas measurements to 1e−9, which pins down exactly which circuit Atlas ran, and a replay mode rebuilds every output from the cache with no key and no network.

**Technical description:**
Python 3.11+, installable with pip, CLI commands measure, image, audio, video and replay. Engines: otoc-echo-v1, blur-v1, telablur-v1. The client caches by content hash, resumes timed-out jobs without paying twice and checks parameters against the live schema. 32 pytest tests, including a replay test with the network blocked. Docs with architecture diagrams in docs/CLI.md.

---

## 10 Quantum-native 2

**Title:** SCRAMBLED: the workflow notebook

**Elevator pitch:** A Python notebook that walks through the whole SCRAMBLED pipeline on the Atlas API, from a raw job to a scrambled video, and maps where scrambling switches on.

**Project description:**
The notebook shows how I built SCRAMBLED from the Atlas API, one step at a time. It starts with one raw API call made by hand, upload, process, poll and download, then moves to the package. It measures a scrambling run and a Clifford control on otoc-echo-v1, checks both against a classical simulation, and then adds a new result: a sweep of ten coupling values showing scrambling switching on between the two non-scrambling ends. From there it turns the measurement into media, image ladders, an echo and a short scrambled video, all displayed inline. It runs in replay mode by default, so a reader without a key can execute every cell, and it records every job id and credit spent.

**Technical description:**
Jupyter, Python 3.14. Engines: otoc-echo-v1 (17 runs including the sweep), blur-v1, telablur-v1; tomography-api-v2 and retrocausal-echo-v1 were attempted and timed out, which the notebook states. Atlas results match the classical statevector to about 1e−13. The notebook is saved with its outputs, ships with an HTML export, and re-executes from the cache with no key and no network.

---

## 11 FQxI Challenge

**Title:** Why you can't unscramble an egg (quantum edition)

**Elevator pitch:** A two-minute animated explainer about the quantum butterfly effect, built from real measurements on Moth Atlas and narrated over a pan of eggs.

**Project description:**
Everyone knows you cannot unscramble an egg, and this explainer uses that to teach information scrambling. A row of twelve eggs stands for twelve qubits; we nudge the middle one, run the circuit forward and backward, and ask whether the nudge comes back. Every chart in the video is a real otoc-echo-v1 measurement from Moth Atlas. Viewers see the disturbance spread one neighbour per step inside a light cone, a control setting where it never spreads at all, a scrambling setting where it is smeared across the whole chain, and a partial return around step fifteen because the chain is short. The last section explains why physicists care, from black holes to testing quantum computers, and is careful about what this small emulator run can and cannot show.

**Technical description:**
Engines: otoc-echo-v1 (two measured maps), blur-v1 and telablur-v1 (egg imagery). Every chart is drawn from the returned data, and the renderer checks the definition of F against the engine documentation each time it loads. Animated in Python with matplotlib and Pillow at 1920×1080, with captions burned in and narration recorded by me. Accuracy notes, sources and job ids are in edu/NOTES.md.
