import * as THREE from 'three';

const S = window.SCENE;
const [NLAT, NLON] = S.grid;
const NV = NLAT * NLON;
const NSITE = 12, NSTEP = 32;

// ---------------------------------------------------------------- timeline (seconds)
export const TL = { title: [0, 4], intro: [4, 8], echo: [8, 32], inside: [32, 37], control: [37, 41], end: [41, 45] };
export const DURATION = TL.end[1];

const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const smooth = (a, b, x) => { const t = clamp((x - a) / (b - a)); return t * t * (3 - 2 * t); };
const fadeWin = (t, a, b, f = 0.6) => smooth(a, a + f, t) * (1 - smooth(b - f, b, t));

// ---------------------------------------------------------------- measured data
function grid(name, key) { return S.otoc[name][key]; }           // [site][t]
// Value at continuous echo time tc in [0, 32]; tc = 0 is "before the kick" (F = 1).
function fieldAt(name, key, site, tc) {
  const g = grid(name, key);
  const at = (k) => (k <= 0 ? 1 : g[site][Math.min(k, NSTEP) - 1]);
  const k0 = Math.floor(tc), f = tc - k0;
  const w = f * f * (3 - 2 * f);
  return at(k0) * (1 - w) + at(k0 + 1) * w;
}
// site k sits at polar angle (k + 0.5) / 12 * pi: site 0 = top (pointy) pole, kick site 6 just below the equator
function rowSiteBlend(i) {
  const theta = (i / (NLAT - 1)) * NSITE - 0.5;
  const k0 = clamp(Math.floor(theta), 0, NSITE - 1), k1 = clamp(k0 + 1, 0, NSITE - 1);
  return [k0, k1, clamp(theta - k0)];
}
const ROW = Array.from({ length: NLAT }, (_, i) => rowSiteBlend(i));

// ---------------------------------------------------------------- deterministic RNG + Voronoi shell fragments
function mulberry(a) { return () => { a |= 0; a = (a + 0x6D2B79F5) | 0; let t = Math.imul(a ^ (a >>> 15), 1 | a);
  t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
const rnd = mulberry(20261004);
const seeds = S.crack_seeds;                                       // same 90 seeds the blur-core crack relief used
const cellRand = seeds.map(() => rnd());

// ---------------------------------------------------------------- geometry
function dirOf(i, j) {
  const th = (i / (NLAT - 1)) * Math.PI, ph = (j / NLON) * 2 * Math.PI;
  // egg axis (+z in the grid) -> +y in the scene
  return [Math.sin(th) * Math.cos(ph), Math.cos(th), -Math.sin(th) * Math.sin(ph)];
}
const DIRS = new Float32Array(NV * 3);
for (let i = 0; i < NLAT; i++) for (let j = 0; j < NLON; j++) DIRS.set(dirOf(i, j), (i * NLON + j) * 3);
const INDEX = [];
for (let i = 0; i < NLAT - 1; i++) for (let j = 0; j < NLON; j++) {
  const a = i * NLON + j, b = i * NLON + (j + 1) % NLON, c = (i + 1) * NLON + j, e = (i + 1) * NLON + (j + 1) % NLON;
  INDEX.push(a, b, c, b, e, c);
}
const flat = (g) => Float32Array.from(g.flat());
const R = Object.fromEntries(Object.entries(S.radii).map(([k, v]) => [k, flat(v)]));

function makeGeometry(radii) {
  const g = new THREE.BufferGeometry();
  const pos = new Float32Array(NV * 3);
  for (let v = 0; v < NV; v++) for (let c = 0; c < 3; c++) pos[v * 3 + c] = DIRS[v * 3 + c] * radii[v];
  g.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  g.setIndex(INDEX);
  g.computeVertexNormals();
  return g;
}

// shell: per-vertex cell id, distance-to-crack, cell direction
const shellGeo = makeGeometry(R.base);
const SEED_ROW = new Int32Array(NV);                               // latitude row of each vertex's fragment seed
{
  const cell = new Float32Array(NV), edge = new Float32Array(NV), crand = new Float32Array(NV), cdir = new Float32Array(NV * 3);
  for (let v = 0; v < NV; v++) {
    const i = Math.floor(v / NLON), j = v % NLON;
    const th = (i / (NLAT - 1)) * Math.PI, ph = (j / NLON) * 2 * Math.PI;
    const p = [Math.sin(th) * Math.cos(ph), Math.sin(th) * Math.sin(ph), Math.cos(th)];  // grid frame (python)
    let b1 = -9, b2 = -9, id = 0;
    seeds.forEach((s, k) => { const d = p[0] * s[0] + p[1] * s[1] + p[2] * s[2];
      if (d > b1) { b2 = b1; b1 = d; id = k; } else if (d > b2) b2 = d; });
    cell[v] = id; edge[v] = b1 - b2; crand[v] = cellRand[id];
    const s = seeds[id]; cdir.set([s[0], s[2], -s[1]], v * 3);
    SEED_ROW[v] = Math.round((Math.acos(clamp(s[2], -1, 1)) / Math.PI) * (NLAT - 1));
  }
  shellGeo.setAttribute('aCellS', new THREE.BufferAttribute(new Float32Array(NV), 1));
  shellGeo.setAttribute('aCell', new THREE.BufferAttribute(cell, 1));
  shellGeo.setAttribute('aEdge', new THREE.BufferAttribute(edge, 1));
  shellGeo.setAttribute('aRand', new THREE.BufferAttribute(crand, 1));
  shellGeo.setAttribute('aCellDir', new THREE.BufferAttribute(cdir, 3));
  shellGeo.setAttribute('aS', new THREE.BufferAttribute(new Float32Array(NV), 1));
  shellGeo.setAttribute('aRe', new THREE.BufferAttribute(new Float32Array(NV).fill(1), 1));
}
const interiorGeo = makeGeometry(R.crack_s000);

// ---------------------------------------------------------------- entanglement-shader-v1 LUTs (as the engine's GLSL expects)
function lutTex(arr) {
  const t = new THREE.DataTexture(Float32Array.from(arr), S.lut.w, S.lut.h, THREE.RedFormat, THREE.FloatType);
  t.wrapS = THREE.RepeatWrapping; t.wrapT = THREE.ClampToEdgeWrapping;
  t.magFilter = t.minFilter = THREE.LinearFilter; t.flipY = false; t.generateMipmaps = false; t.needsUpdate = true;
  return t;
}
const uR = lutTex(S.lut.R), uT = lutTex(S.lut.T);

const ENV_GLSL = /* glsl */`
  float disc(vec3 d, vec3 c, float r, float soft) { return smoothstep(cos(r + soft), cos(r), dot(d, normalize(c))); }
  vec3 studio(vec3 d) {
    vec3 c = mix(vec3(0.015, 0.018, 0.03), vec3(0.09, 0.11, 0.17), smoothstep(-0.3, 0.9, d.y));
    c += vec3(7.0, 6.8, 6.4) * disc(d, vec3(-0.55, 0.75, 0.45), 0.33, 0.12);   // key softbox
    c += vec3(2.0, 2.6, 3.4) * disc(d, vec3(0.95, 0.25, -0.35), 0.16, 0.10);  // cool rim
    c += vec3(2.2, 1.4, 0.8) * disc(d, vec3(-0.7, 0.05, -0.75), 0.30, 0.20);   // warm fill
    c += vec3(1.2) * disc(d, vec3(0.3, 0.95, -0.1), 0.6, 0.4);                  // top bounce
    c *= mix(0.25, 1.0, smoothstep(-0.25, 0.05, d.y));                           // dark floor
    return c;
  }`;

const shellMat = new THREE.ShaderMaterial({
  transparent: true, side: THREE.DoubleSide, depthWrite: true,
  uniforms: { uRTexture: { value: uR }, uTTexture: { value: uT }, uThickness: { value: 500 },
              uSpec: { value: 1.0 }, uTrans: { value: 0.55 }, uTime: { value: 0 } },
  vertexShader: /* glsl */`
    attribute float aS, aRe, aCell, aEdge, aRand, aCellS; attribute vec3 aCellDir;
    varying vec3 vN, vW; varying float vS, vRe, vCell, vEdge, vLift;
    void main() {
      float reveal = aS * 1.3;
      // whole fragment moves rigidly, driven by the scrambling at its seed's latitude
      float lift = smoothstep(0.78 + aRand * 0.5, 0.98 + aRand * 0.5, aCellS * 1.3);
      float groove = exp(-pow(aEdge / (0.002 + 0.004 * reveal), 2.0)) * reveal;
      vec3 p = position * (1.0 - 0.025 * groove) + aCellDir * (0.16 * lift) + vec3(0.0, -0.05, 0.0) * lift * lift;
      vec4 w = modelMatrix * vec4(p, 1.0);
      vW = w.xyz; vN = normalize(mat3(modelMatrix) * normal);
      vS = aS; vRe = aRe; vCell = aCell; vEdge = aEdge; vLift = lift;
      gl_Position = projectionMatrix * viewMatrix * w;
    }`,
  fragmentShader: /* glsl */`
    uniform sampler2D uRTexture, uTTexture; uniform float uThickness, uSpec, uTrans;
    varying vec3 vN, vW; varying float vS, vRe, vCell, vEdge, vLift;
    ${ENV_GLSL}
    const float ET_PI_2 = 1.5707963267948966; const float ET_TWO_PI = 6.283185307179586;
    void main() {
      if (fwidth(vCell) > 0.01 && vLift > 0.02) discard;          // torn triangle between two flying fragments
      float reveal = vS * 1.3;
      float open = 0.0008 + 0.0042 * smoothstep(0.15, 1.0, reveal);
      if (reveal > 0.12 && vEdge < open) discard;                 // crack gap
      vec3 N = normalize(vN); vec3 V = normalize(cameraPosition - vW);
      if (!gl_FrontFacing) N = -N;
      // ---- entanglement-shader-v1 GLSL (engine output, verbatim maths) -------------------------
      float thickness = uThickness * (1.0 + 0.22 * (1.0 - vRe));   // measured Re F shifts the stack spacing
      float cosTheta = abs(dot(N, V));
      float theta = acos(clamp(cosTheta, 0.0, 1.0));
      float D = -2.0 * ET_TWO_PI * thickness * cosTheta;
      const vec3 wavelength = vec3(650.0, 530.0, 470.0);
      float s0 = mod(D / wavelength.r, ET_TWO_PI) / ET_TWO_PI;
      float s1 = mod(D / wavelength.g, ET_TWO_PI) / ET_TWO_PI;
      float s2 = mod(D / wavelength.b, ET_TWO_PI) / ET_TWO_PI;
      float t = theta / ET_PI_2;
      vec3 Rf = vec3(texture(uRTexture, vec2(s0, t)).r, texture(uRTexture, vec2(s1, t)).r, texture(uRTexture, vec2(s2, t)).r);
      vec3 Tf = vec3(texture(uTTexture, vec2(s0, t)).r, texture(uTTexture, vec2(s1, t)).r, texture(uTTexture, vec2(s2, t)).r);
      // ---- BSDF = R * specular + T * transparent (as in the engine's OSL) -------------------
      vec3 refl = studio(reflect(-V, N));
      vec3 Ldir = normalize(vec3(-0.55, 0.75, 0.45));
      vec3 shellBase = vec3(0.93, 0.86, 0.76) * (0.10 + 0.55 * max(dot(N, Ldir), 0.0));
      vec3 col = Rf * refl * uSpec + shellBase * Rf * 0.75;
      float edgeGlow = exp(-pow((vEdge - open) / 0.0025, 2.0)) * smoothstep(0.1, 0.5, reveal);
      col += vec3(1.0, 0.62, 0.22) * edgeGlow * 1.6;
      float trans = clamp(dot(Tf, vec3(0.3333)), 0.0, 1.0);
      float alpha = clamp(1.0 - uTrans * trans, 0.72, 1.0);
      alpha = max(alpha, edgeGlow);
      alpha *= 1.0 - smoothstep(0.55, 1.0, vLift);
      gl_FragColor = vec4(col, alpha);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
});

const interiorMat = new THREE.ShaderMaterial({
  uniforms: { uHeat: { value: 0 } },
  vertexShader: /* glsl */`
    varying vec3 vN, vW, vO;
    void main() { vO = position; vec4 w = modelMatrix * vec4(position, 1.0); vW = w.xyz;
      vN = normalize(mat3(modelMatrix) * normal); gl_Position = projectionMatrix * viewMatrix * w; }`,
  fragmentShader: /* glsl */`
    uniform float uHeat; varying vec3 vN, vW, vO;
    ${ENV_GLSL}
    float h3(vec3 p) { return fract(sin(dot(p, vec3(127.1, 311.7, 74.7))) * 43758.5453); }
    float vnoise(vec3 p) { vec3 i = floor(p), f = fract(p); f = f * f * (3.0 - 2.0 * f);
      return mix(mix(mix(h3(i), h3(i + vec3(1,0,0)), f.x), mix(h3(i + vec3(0,1,0)), h3(i + vec3(1,1,0)), f.x), f.y),
                 mix(mix(h3(i + vec3(0,0,1)), h3(i + vec3(1,0,1)), f.x), mix(h3(i + vec3(0,1,1)), h3(i + vec3(1,1,1)), f.x), f.y), f.z); }
    void main() {
      float n = vnoise(vO * 14.0) * 0.6 + vnoise(vO * 31.0) * 0.4;
      vec3 curd = vec3(vnoise(vO * 9.0 + 3.1), vnoise(vO * 9.0 + 7.7), vnoise(vO * 9.0 + 1.3)) - 0.5;
      vec3 N = normalize(normalize(vN) + 0.6 * curd);
      vec3 V = normalize(cameraPosition - vW);
      vec3 L = normalize(vec3(-0.55, 0.75, 0.45));
      vec3 yolk = mix(vec3(1.0, 0.70, 0.16), vec3(1.0, 0.90, 0.55), smoothstep(0.35, 0.8, n));
      float wrap = clamp((dot(N, L) + 0.45) / 1.45, 0.0, 1.0);
      vec3 col = yolk * (0.12 + 1.15 * wrap) + yolk * vec3(1.0, 0.5, 0.2) * pow(1.0 - abs(dot(N, V)), 2.0) * 0.6;
      col += studio(reflect(-V, N)) * 0.06 * smoothstep(0.4, 0.9, n);
      col += vec3(1.0, 0.45, 0.12) * uHeat * 0.15;
      gl_FragColor = vec4(col, 1.0);
      #include <tonemapping_fragment>
      #include <colorspace_fragment>
    }`,
});

const floorMat = new THREE.ShaderMaterial({
  transparent: true, depthWrite: false,
  uniforms: { uGlow: { value: 0 } },
  vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
  fragmentShader: /* glsl */`
    uniform float uGlow; varying vec2 vUv;
    void main() { float r = length(vUv - 0.5) * 2.0;
      float shadow = exp(-r * r * 60.0) * 0.85 + exp(-r * r * 9.0) * 0.35;
      vec3 glow = vec3(1.0, 0.6, 0.25) * exp(-r * r * 14.0) * uGlow;
      gl_FragColor = vec4(glow, clamp(shadow + length(glow), 0.0, 1.0)); }`,
});

// ---------------------------------------------------------------- scene
const canvas = document.getElementById('gl');
const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(window.__PIXEL_RATIO || 2);
renderer.setSize(1080, 1080, false);
renderer.setClearColor(0x000000, 0);
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;
renderer.outputColorSpace = THREE.SRGBColorSpace;

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(30, 1, 0.05, 50);
const egg = new THREE.Group();
egg.position.y = 0.06;
scene.add(egg);
const interior = new THREE.Mesh(interiorGeo, interiorMat);
const shell = new THREE.Mesh(shellGeo, shellMat);
egg.add(interior, shell);
const floor = new THREE.Mesh(new THREE.PlaneGeometry(2.6, 2.6), floorMat);
floor.rotation.x = -Math.PI / 2;
floor.position.y = egg.position.y - 0.5 - 0.005;
scene.add(floor);
shell.renderOrder = 2; interior.renderOrder = 1;

// ---------------------------------------------------------------- per-frame state
const aS = shellGeo.getAttribute('aS'), aRe = shellGeo.getAttribute('aRe'), aCellS = shellGeo.getAttribute('aCellS');
// blur-core outputs are rescaled to the input max; shrink each uniformly so it fits inside the shell
const MORPH = [R.crack_s000, R.crack_s035, R.crack_s060, R.crack_s060_r05, R.crack_s090_r10]
  .map((a) => { let k = Infinity; a.forEach((x, v) => { k = Math.min(k, R.base[v] / Math.max(x, 1e-6)); });
    return a.map((x) => x * k * 0.97); });
const ipos = interiorGeo.getAttribute('position');
const rowS = new Float32Array(NLAT), rowRe = new Float32Array(NLAT);
let lastMorph = -1;

function setInterior(w) {
  const q = Math.round(w * 200) / 200;
  if (q === lastMorph) return;
  lastMorph = q;
  const x = q * (MORPH.length - 1), k = Math.min(Math.floor(x), MORPH.length - 2), f = x - k;
  const A = MORPH[k], B = MORPH[k + 1];
  for (let v = 0; v < NV; v++) {
    const r = A[v] * (1 - f) + B[v] * f;
    ipos.array[v * 3] = DIRS[v * 3] * r; ipos.array[v * 3 + 1] = DIRS[v * 3 + 1] * r; ipos.array[v * 3 + 2] = DIRS[v * 3 + 2] * r;
  }
  ipos.needsUpdate = true;
  interiorGeo.computeVertexNormals();
}

function phaseState(time) {
  if (time < TL.echo[0]) return { name: 'scrambling', tc: 0 };
  if (time < TL.control[0]) return { name: 'scrambling', tc: clamp((time - TL.echo[0]) / (TL.echo[1] - TL.echo[0])) * NSTEP };
  return { name: 'clifford', tc: clamp((time - TL.control[0] - 0.4) / 2.6) * NSTEP };
}

function applyField(name, tc) {
  let mean = 0;
  const site = new Float32Array(NSITE), re = new Float32Array(NSITE);
  for (let k = 0; k < NSITE; k++) {
    site[k] = 1 - Math.abs(fieldAt(name, 'absF', k, tc));
    re[k] = fieldAt(name, 'reF', k, tc);
    mean += site[k] / NSITE;
  }
  for (let i = 0; i < NLAT; i++) { const [a, b, f] = ROW[i];
    rowS[i] = site[a] * (1 - f) + site[b] * f; rowRe[i] = re[a] * (1 - f) + re[b] * f; }
  for (let v = 0; v < NV; v++) { const i = (v / NLON) | 0; aS.array[v] = rowS[i]; aRe.array[v] = rowRe[i];
    aCellS.array[v] = rowS[SEED_ROW[v]]; }
  aS.needsUpdate = aRe.needsUpdate = aCellS.needsUpdate = true;
  return mean;
}

// ---------------------------------------------------------------- HUD + text
const heat = document.getElementById('heat').getContext('2d');
function drawHeat(name, tc) {
  const g = grid(name, 'absF'), cw = 8, ch = 8;
  heat.clearRect(0, 0, 256, 96);
  for (let t = 0; t < NSTEP; t++) for (let k = 0; k < NSITE; k++) {
    const s = 1 - Math.abs(g[k][t]);
    const on = t + 1 <= tc + 1e-6 ? 1 : 0.13;
    const r = Math.round(40 + 215 * s), gg = Math.round(60 + 120 * s * (1 - s) * 2.5), b = Math.round(120 + 100 * (1 - s));
    heat.fillStyle = `rgba(${r},${gg},${b},${on})`;
    heat.fillRect(t * cw, k * ch, cw - 1, ch - 1);
  }
  if (tc >= 1) { heat.strokeStyle = '#ffffff'; heat.lineWidth = 1.5;
    heat.strokeRect((Math.ceil(tc) - 1) * cw - 0.5, -0.5, cw, 96); }
}

const CAPTIONS = [
  [TL.intro[0], TL.intro[1], 'A 3D egg, shaded by the Entanglement Shader',
   'entanglement-shader-v1: reflectance + transmittance tables for a 3-layer, 8-ray quantum stack'],
  [8.0, 12.6, 'A one-qubit kick at site 6, just below the equator',
   '12 qubits → 12 latitude bands · the shell cracks where the measured |F(site, t)| falls below 1'],
  [12.6, 17.6, 'The light cone reaches the poles: the chain is scrambled',
   'otoc-echo-v1, 12-site chain, θx = 0.3π, θzz = 0.35π · Re F also shifts the shell colour'],
  [17.6, 20.8, 'Finite-size revival near t ≈ 13–16',
   'on a chain this small, part of the signal briefly refocuses: fragments drift back'],
  [20.8, 32.0, 'Not destroyed, only spread out',
   'the kick is still in the 12-qubit state, but no single site can read it back (|F| ≈ 0.3)'],
  [TL.inside[0], TL.inside[1], 'Inside: the egg mesh, quantum-blurred',
   'mesh → 128×128 radius grid (14 qubits) → blur-core-v1, reach 1.0 → mesh'],
  [TL.control[0], TL.control[1], 'Control: θzz = π makes the circuit Clifford',
   'measured |F| = 1 at every site and step · no scrambling · the egg stays whole'],
];

const el = (id) => document.getElementById(id);
const blurJobs = S.blur_jobs;
el('endrows').innerHTML = [
  `otoc-echo-v1 · 12-site chain · depth 32 · θx = 0.3π · θzz = 0.35π (control θzz = π)`,
  `entanglement-shader-v1 · job ${S.lut.job_id.slice(0, 8)} · 3 layers · 8 rays · frustrated`,
  `blur-core-v1 · ${Object.keys(blurJobs).length} jobs on the egg mesh · zero-blur round trip verified`,
].join('<br>');
el('endfine').innerHTML = 'Quantum steps ran on Moth Atlas (Qiskit Aer emulator, exact).<br>' +
  'Mesh, data-to-geometry mapping, shading and rendering are classical (three.js).';

function setText(time) {
  el('title').style.opacity = fadeWin(time, -1, TL.title[1], 0.8);
  el('end').style.opacity = smooth(TL.end[0], TL.end[0] + 0.8, time);
  el('hudlayer').style.opacity = fadeWin(time, TL.intro[0] + 0.5, TL.end[0] + 0.3, 0.6);
  let html = '', op = 0;
  for (const [a, b, big, small] of CAPTIONS) if (time >= a && time < b) { html = `${big}<small>${small}</small>`; op = fadeWin(time, a, b, 0.45); }
  el('caption').innerHTML = html; el('caption').style.opacity = op;
}

// ---------------------------------------------------------------- render one frame at time (s)
window.renderAt = function (time) {
  const ph = phaseState(time);
  const mean = applyField(ph.name, ph.tc);
  const echoDone = time >= TL.echo[0] ? clamp((time - TL.echo[0]) / (TL.echo[1] - TL.echo[0])) : 0;
  // interior morph follows global scrambling during the echo, then completes on "inside"
  let w = clamp(mean / 0.72);
  if (time >= TL.inside[0] && time < TL.control[0]) w = Math.max(w, smooth(TL.inside[0], TL.inside[0] + 3, time));
  if (ph.name === 'clifford') w = 0;
  setInterior(w);
  interiorMat.uniforms.uHeat.value = mean;
  floorMat.uniforms.uGlow.value = 0.35 * mean;

  // camera: slow orbit, gentle push in; close-up while looking inside
  const ang = 0.7 + time * 0.17;
  let rad = 3.15 - 0.45 * smooth(0, TL.echo[1], time);
  let hgt = 0.55 + 0.12 * Math.sin(time * 0.21);
  if (time >= TL.inside[0] && time < TL.control[0]) { const c = fadeWin(time, TL.inside[0], TL.control[0], 1.4); rad -= 0.55 * c; hgt += 0.5 * c; }
  if (ph.name === 'clifford') { rad = 2.9; }
  camera.position.set(Math.cos(ang) * rad, egg.position.y + hgt, Math.sin(ang) * rad);
  camera.lookAt(0, egg.position.y - 0.02, 0);

  // fade through black into the control segment
  const dip = clamp(Math.abs(time - TL.control[0]) / 0.45);
  canvas.style.opacity = dip * (1 - 0.55 * smooth(TL.end[0], TL.end[0] + 0.8, time));

  el('tval').textContent = `t = ${Math.min(NSTEP, Math.ceil(ph.tc - 1e-6))} / 32` + (ph.name === 'clifford' ? '  ·  control' : '');
  drawHeat(ph.name, ph.tc);
  setText(time);
  renderer.render(scene, camera);
  return { mean, tc: ph.tc, phase: ph.name };
};

window.__debugInterior = (name, ang = 0.7) => {
  const r = R[name]; shell.visible = false; lastMorph = -1;
  for (let v = 0; v < NV; v++) for (let c = 0; c < 3; c++) ipos.array[v * 3 + c] = DIRS[v * 3 + c] * r[v];
  ipos.needsUpdate = true; interiorGeo.computeVertexNormals();
  for (const id of ['title', 'end', 'hudlayer']) el(id).style.opacity = 0;
  el('caption').innerHTML = name; el('caption').style.opacity = 1;
  camera.position.set(Math.cos(ang) * 2.6, 0.7, Math.sin(ang) * 2.6); camera.lookAt(0, 0.04, 0);
  renderer.render(scene, camera);
};

window.__info = () => {
  const gl = renderer.getContext();
  const ext = gl.getExtension('WEBGL_debug_renderer_info');
  return { renderer: ext ? gl.getParameter(ext.UNMASKED_RENDERER_WEBGL) : 'unknown', duration: DURATION, verts: NV };
};
window.__ready = true;
