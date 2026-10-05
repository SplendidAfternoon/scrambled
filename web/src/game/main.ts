import { AtlasError, keyStore, measureOtoc, otocParams, pickRoute } from "../lib/atlas";
import { fmtPi, loadFeatured, loadGrid, loadSprites, shortId, type SpriteMeta } from "../lib/data";
import { drawHeatmap, fitCanvas } from "../lib/draw";
import { absFat, arrival, cooked, depth, Fat, meanAbs, sites, snapClifford, type Run } from "../lib/otoc";
import { Sfx } from "./audio";
import { LEVELS } from "./levels";
import { advance, judge, newRun, targets, winningSteps, type Level, type PanChoice, type RunState, type Verdict } from "./rules";
import { findRun } from "./runs";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const screens = ["s-title", "s-choose", "s-cook", "s-result", "s-end"] as const;
type Screen = (typeof screens)[number];
function show(s: Screen) {
  for (const id of screens) $(id).hidden = id !== s;
  window.scrollTo({ top: 0 });
}

const sfx = new Sfx();
const route = pickRoute(location);
const BEST_KEY = "scrambled.best";

/* ---------------- sprites ---------------- */
const SPRITE_NAMES = ["egg_fresh", "egg_crack", "egg_cook", "egg_burnt", "egg_scrambled", "egg_scrambled_hot"] as const;
type SpriteName = (typeof SPRITE_NAMES)[number];
const sprites = {} as Record<SpriteName, HTMLImageElement>;
let spriteMeta: Record<string, SpriteMeta> = {};

function spriteUrl(name: SpriteName): string {
  const m = spriteMeta[name];
  if (m && m.job_id && !m.error) return `sprites/${name}.png`;
  return name.startsWith("egg_scrambled") ? "sprites/src/egg_scrambled.png" : "sprites/src/egg_whole.png";
}

async function loadSpriteImages() {
  try {
    spriteMeta = await loadSprites();
  } catch {
    spriteMeta = {};
  }
  await Promise.all(
    SPRITE_NAMES.map(
      (n) =>
        new Promise<void>((res) => {
          const im = new Image();
          im.onload = () => res();
          im.onerror = () => res();
          im.src = spriteUrl(n);
          sprites[n] = im;
        }),
    ),
  );
  for (const el of document.querySelectorAll<HTMLImageElement>("img[data-sprite]")) el.src = spriteUrl(el.dataset.sprite as SpriteName);
  const fromAtlas = SPRITE_NAMES.filter((n) => spriteMeta[n]?.job_id && !spriteMeta[n]?.error);
  const engines = [...new Set(fromAtlas.map((n) => spriteMeta[n].engine_id))].join(" and ");
  const how: Record<string, string> = {
    "tessa-image-v1": "Tessa's quantum colour encoder (fewer shots = a more cooked egg)",
    "blur-v1": "Quantum Blur at rising strength",
  };
  $("e-credit").textContent = !fromAtlas.length
    ? "Sprites: plain crops of photos of real eggs."
    : `Sprites: photos of real eggs, sent through Moth Atlas's ${engines} (${[...new Set(fromAtlas.map((n) => how[spriteMeta[n].engine_id!] ?? ""))].filter(Boolean).join("; ")})${fromAtlas.length < SPRITE_NAMES.length ? `; ${SPRITE_NAMES.length - fromAtlas.length} are plain crops` : ""}.`;
}

/* ---------------- state ---------------- */
let runs: Run[] = [];
let state: RunState & { over?: boolean; cleared?: boolean } = newRun();
let level: Level = LEVELS[0];
let choice: PanChoice;
let run: Run;
let t = 1;
let cooking = false;
let ready = false;
let lastFrame = 0;
let lastStep = 1;
const custom = new Map<number, { choice: PanChoice; run: Run }[]>();

function livesHtml() {
  return Array.from({ length: 3 }, (_, i) => `<img src="${spriteUrl("egg_fresh")}" class="${i < state.lives ? "" : "lost"}" alt="${i < state.lives ? "life" : "lost life"}" />`).join("");
}
function hud(prefix: "c" | "k") {
  $(`${prefix}-level`).textContent = `LEVEL ${state.level + 1}/${LEVELS.length}`;
  $(`${prefix}-lives`).innerHTML = livesHtml();
  $(`${prefix}-score`).textContent = `${state.score} pts`;
}

/* ---------------- choose screen ---------------- */
function choicesFor(l: Level) {
  const base = l.choices.map((c) => ({ choice: c, run: findRun(runs, c)! })).filter((x) => x.run);
  return [...base, ...(custom.get(l.id) ?? [])];
}

function showChoose() {
  level = LEVELS[state.level];
  hud("c");
  $("c-title").textContent = `${level.id}. ${level.title}`;
  $("c-blurb").textContent = level.blurb;
  $("c-rules").innerHTML = `
    <span class="tag">${level.targetOffsets.length} golden eggs</span>
    <span class="tag">keep them ${Math.round(level.threshold * 100)}% whole</span>
    <span class="tag">${level.seconds} s on the clock</span>`;
  $("c-pick").textContent = choicesFor(level).length > 1 ? "Pick a pan:" : "Your pan:";
  const box = $("c-choices");
  box.innerHTML = "";
  for (const { choice: c, run: r } of choicesFor(level)) {
    const b = document.createElement("button");
    b.className = "choice";
    const heat = c.flames === 0 ? `<span class="lid">lid on</span>` : Array.from({ length: 3 }, (_, i) => `<i class="${i < c.flames ? "on" : ""}"></i>`).join("");
    b.innerHTML = `<div class="heat" aria-hidden="true">${heat}</div><h3>${c.label}</h3><p>${c.hint}</p><div class="params" title="θx ${fmtPi(c.theta_x_pi)} · θzz ${fmtPi(c.theta_zz_pi)} · job ${r.job_id}">measured on Moth Atlas</div>`;
    b.addEventListener("click", () => {
      sfx.unlock();
      sfx.click();
      startCook(c, r);
    });
    box.appendChild(b);
  }
  show("s-choose");
}

/* live custom pan */
function initLive() {
  const lx = $<HTMLInputElement>("lx");
  const lz = $<HTMLInputElement>("lz");
  const sync = () => {
    $("lx-val").textContent = fmtPi(+lx.value);
    const z = snapClifford(+lz.value);
    $("lz-val").textContent = z === 1 ? "π (Clifford)" : fmtPi(z);
  };
  lx.addEventListener("input", sync);
  lz.addEventListener("input", sync);
  sync();
  $("live-route").textContent = route === "direct" ? " (directly)" : " (through this site's /api/atlas proxy)";
  const key = $<HTMLInputElement>("lkey");
  key.value = keyStore.get();
  const st = $("lstatus");
  $("lgo").addEventListener("click", async () => {
    const k = key.value.trim();
    if (!k && route === "direct") {
      st.textContent = "Paste your Atlas API key first.";
      st.classList.add("err");
      return;
    }
    keyStore.set(k, keyStore.remembered());
    const txp = +lx.value;
    const tzp = snapClifford(+lz.value);
    const forLevel = level.id;
    st.classList.remove("err");
    st.textContent = "Submitting …";
    $<HTMLButtonElement>("lgo").disabled = true;
    try {
      const r = await measureOtoc(otocParams(12, 32, txp, tzp), {
        route,
        key: k,
        timeoutMs: 600_000,
        onStatus: (s) => (st.textContent = `job ${s.job_id ? shortId(s.job_id) : ""} · ${s.status} · ${(s.elapsed / 1000).toFixed(0)} s`),
      });
      const flames = tzp === 1 ? 0 : Math.min(3, Math.max(1, Math.round(txp / 0.1)));
      const c: PanChoice = { label: "Your pan (live)", hint: `Measured just now on Atlas, job ${shortId(r.job_id)}.`, flames, n_sites: 12, theta_x_pi: txp, theta_zz_pi: tzp };
      custom.set(forLevel, [...(custom.get(forLevel) ?? []), { choice: c, run: r }]);
      st.textContent = `Done: job ${r.job_id}. Your pan is in the list above.`;
      if (!$("s-choose").hidden && level.id === forLevel) showChoose();
    } catch (e) {
      st.textContent = (e as AtlasError).message;
      st.classList.add("err");
    } finally {
      $<HTMLButtonElement>("lgo").disabled = false;
    }
  });
}

/* ---------------- cook screen ---------------- */
const pan = $<HTMLCanvasElement>("pan");
interface Puff { x: number; y: number; vy: number; life: number; r: number }
let puffs: Puff[] = [];

function layout(W: number, H: number, n: number) {
  const twoRows = n > 8 || pan.clientWidth < 560;
  const perRow = twoRows ? Math.ceil(n / 2) : n;
  const rows = twoRows ? 2 : 1;
  const size = Math.min((W * 0.86) / perRow, (H * 0.62) / rows);
  const pos: { x: number; y: number }[] = [];
  for (let s = 0; s < n; s++) {
    const row = Math.floor(s / perRow);
    let col = s % perRow;
    if (row === 1) col = perRow - 1 - col; // snake: neighbours stay neighbours
    const x = W / 2 + (col - (perRow - 1) / 2) * size;
    const y = H / 2 + (row - (rows - 1) / 2) * size * 1.15;
    pos.push({ x, y });
  }
  return { pos, size };
}

function smooth(a: number, b: number, x: number) {
  const k = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return k * k * (3 - 2 * k);
}

function drawPan(now: number) {
  const ctx = fitCanvas(pan);
  const W = pan.width;
  const H = pan.height;
  const n = sites(run);
  const d = depth(run);
  const heat = 1 - meanAbs(run, [...Array(n).keys()].filter((s) => s !== run.kick_site), t);
  // stove + pan
  const g = ctx.createRadialGradient(W / 2, H / 2, 10, W / 2, H / 2, W * 0.7);
  g.addColorStop(0, `rgb(${40 + 50 * heat | 0}, ${30 + 10 * heat | 0}, 24)`);
  g.addColorStop(1, "#0b0908");
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, W, H);
  ctx.save();
  ctx.translate(W / 2, H / 2);
  ctx.fillStyle = "#1d1b1a";
  ctx.strokeStyle = "#3a3633";
  ctx.lineWidth = W * 0.012;
  ctx.beginPath();
  ctx.ellipse(0, 0, W * 0.47, H * 0.44, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = `rgba(255, 120, 30, ${0.05 + 0.12 * heat})`;
  ctx.beginPath();
  ctx.ellipse(0, 0, W * 0.4, H * 0.36, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();

  const { pos, size } = layout(W, H, n);
  const tg = new Set(targets(level, run));
  const arr = arrival(run);
  // chain links
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = Math.max(2, size * 0.04);
  ctx.beginPath();
  pos.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
  ctx.stroke();

  for (let s = 0; s < n; s++) {
    const { x, y } = pos[s];
    const m = absFat(run, s, t);
    const re = Fat(run, s, t)[0];
    const c = cooked(run, s, t);
    const wob = (1 - m) * size * 0.06;
    const ang = Math.sin(now / 90 + s * 1.7) * (1 - m) * 0.25;
    const dx = Math.sin(now / 70 + s) * wob;
    if (tg.has(s)) {
      ctx.strokeStyle = ready ? "#7ad17a" : "#ffd54a";
      ctx.lineWidth = Math.max(3, size * 0.07);
      ctx.shadowColor = ready ? "#7ad17a" : "#ffc93c";
      ctx.shadowBlur = size * 0.35;
      ctx.beginPath();
      ctx.arc(x, y, size * 0.5, 0, Math.PI * 2);
      ctx.stroke();
      ctx.shadowBlur = 0;
    }
    ctx.save();
    ctx.translate(x + dx, y);
    ctx.rotate(ang + (re < 0 ? Math.PI : 0));
    const sz = size * 0.86;
    const whole: SpriteName = t >= d ? "egg_burnt" : m >= 0.85 ? "egg_fresh" : m >= 0.6 ? "egg_crack" : "egg_cook";
    const scr = smooth(0.3, 0.9, c);
    ctx.globalAlpha = 1 - scr;
    ctx.drawImage(sprites[whole], -sz / 2, -sz / 2, sz, sz);
    if (scr > 0) {
      ctx.globalAlpha = scr;
      ctx.drawImage(sprites[m < 0.2 ? "egg_scrambled_hot" : "egg_scrambled"], -sz / 2, -sz / 2, sz, sz);
    }
    ctx.globalAlpha = 1;
    ctx.restore();
    if (s === run.kick_site) {
      ctx.strokeStyle = "#ff6b5b";
      ctx.lineWidth = Math.max(2, size * 0.04);
      ctx.setLineDash([size * 0.08, size * 0.06]);
      ctx.beginPath();
      ctx.arc(x, y, size * 0.47, 0, Math.PI * 2);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle = "#ff6b5b";
      ctx.font = `${Math.round(size * 0.24)}px system-ui`;
      ctx.textAlign = "center";
      ctx.fillText("◆", x + size * 0.4, y - size * 0.32);
    }
    if (arr[s] !== null && t >= arr[s]! && Math.random() < 0.15 * (1 - m) + 0.01) {
      puffs.push({ x: x + (Math.random() - 0.5) * size * 0.5, y: y - size * 0.3, vy: size * (0.01 + Math.random() * 0.015), life: 1, r: size * (0.08 + Math.random() * 0.1) });
    }
  }
  // steam
  puffs = puffs.filter((p) => p.life > 0);
  for (const p of puffs) {
    p.y -= p.vy;
    p.life -= 0.02;
    p.r *= 1.012;
    ctx.fillStyle = `rgba(255,255,255,${0.18 * p.life})`;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
    ctx.fill();
  }
  return heat;
}

function updateMeters() {
  const d = depth(run);
  const mem = meanAbs(run, targets(level, run), t);
  ready = t < d && judge(level, run, t).win;
  const cookedEnough = t >= level.minT;
  $("k-t").textContent = cookedEnough ? "done enough" : "still raw";
  $("k-t").dataset.t = t.toFixed(2);
  $("k-fill").style.width = `${((t - 1) / (d - 1)) * 100}%`;
  $("k-mem").textContent = `${Math.round(mem * 100)}%`;
  const mf = $("k-memfill");
  mf.style.width = `${mem * 100}%`;
  mf.classList.toggle("low", mem < level.threshold);
  const btn = $<HTMLButtonElement>("serve");
  btn.classList.toggle("ready", ready);
  btn.textContent = ready ? "SERVE NOW" : "SERVE";
  return mem;
}

function frame(now: number) {
  if (!cooking) return;
  const dt = lastFrame ? Math.min(0.1, (now - lastFrame) / 1000) : 0;
  lastFrame = now;
  const d = depth(run);
  t = Math.min(d, t + (dt * (d - 1)) / level.seconds);
  const heat = drawPan(now);
  sfx.setHeat(heat);
  const mem = updateMeters();
  if (Math.floor(t) > lastStep) {
    lastStep = Math.floor(t);
    sfx.ping(mem);
  }
  if (t >= d) {
    serve();
    return;
  }
  requestAnimationFrame(frame);
}

function startCook(c: PanChoice, r: Run) {
  choice = c;
  run = r;
  t = 1;
  lastStep = 1;
  lastFrame = 0;
  puffs = [];
  hud("k");
  const d = depth(run);
  const z = $("k-zone");
  z.style.left = `${((level.minT - 1) / (d - 1)) * 100}%`;
  z.style.right = "0";
  $("k-thr").style.left = `${level.threshold * 100}%`;
  $("k-prov").textContent = `${c.label} · every egg follows a real measurement from Moth Atlas (otoc-echo-v1, job ${shortId(r.job_id)})`;
  $("stamp").hidden = true;
  $<HTMLButtonElement>("serve").disabled = false;
  updateMeters();
  show("s-cook");
  sfx.startSizzle();
  cooking = true;
  requestAnimationFrame(frame);
}

const STAMP: Record<Verdict["outcome"], string> = { raw: "RAW!", scrambled: "SCRAMBLED!", served: "SERVED", perfect: "PERFECT!", burnt: "BURNT!" };

function serve() {
  if (!cooking) return;
  cooking = false;
  sfx.stopSizzle();
  const v = judge(level, run, t);
  drawPan(performance.now());
  const stamp = $("stamp");
  stamp.textContent = STAMP[v.outcome];
  stamp.className = `stamp ${v.win ? "good" : "bad"}`;
  stamp.hidden = false;
  $<HTMLButtonElement>("serve").disabled = true;
  $("serve").classList.remove("ready");
  if (v.win) sfx.win(v.outcome === "perfect");
  else {
    sfx.lose();
    const w = $("pan-wrap");
    w.classList.remove("shake");
    void w.offsetWidth;
    w.classList.add("shake");
  }
  const prev = state.level;
  state = advance(state, v, LEVELS.length);
  setTimeout(() => showResult(v, prev), 1100);
}

/* ---------------- result / end ---------------- */
function why(v: Verdict, l: Level, r: Run, c: PanChoice): string {
  const tg = targets(l, r);
  const arr = arrival(r);
  const firstHit = Math.min(...tg.map((s) => arr[s] ?? Infinity));
  const win = winningSteps(l, r);
  const d = depth(r);
  const pct = (x: number) => `${Math.round(x * 100)}%`;
  const when = (step: number) => (step / d < 0.34 ? "early" : step / d < 0.67 ? "about halfway" : "late");
  const windowTxt = win.length
    ? `With this pan the moment to serve was ${when(win[0])} in the cook${win.length <= 2 ? ", and it was brief" : ""}. Watch for the SERVE NOW button.`
    : "This pan never works for this level, so try another one.";
  const cone = Number.isFinite(firstHit) && firstHit < v.t ? " The crack had already reached them." : "";
  switch (v.outcome) {
    case "raw":
      return `Too early: the eggs were still raw. Wait for the cook bar to reach the green zone. ${windowTxt}`;
    case "burnt":
      return `The clock ran out and the eggs burnt. ${windowTxt}`;
    case "scrambled":
      return `The golden eggs were only ${pct(v.memory)} whole and you needed ${pct(l.threshold)}.${cone} ${windowTxt}`;
    default: {
      let physics = "";
      if (c.theta_zz_pi === 1) physics = "Under the Clifford lid the crack still moves from egg to egg, but it never smears out, so nothing scrambles. In a real quantum circuit made only of Clifford gates, that is guaranteed.";
      else if (v.t >= 13 && firstHit <= v.t) physics = "You caught the echo. The scramble bounced off the edge of the pan and briefly put the golden eggs back together, which really happens in a short chain of qubits.";
      else physics = "You served before the crack reached them.";
      return `The golden eggs were ${pct(v.memory)} whole. ${physics}`;
    }
  }
}

function showResult(v: Verdict, levelIdx: number) {
  const l = LEVELS[levelIdx];
  const verdict = $("r-verdict");
  verdict.textContent = STAMP[v.outcome];
  verdict.className = `verdict ${v.win ? "good" : "bad"}`;
  $("r-score").textContent = v.win ? `+${v.score} pts` : `${state.lives} ${state.lives === 1 ? "life" : "lives"} left`;
  $("r-why").textContent = why(v, l, run, choice);
  $("r-prov").textContent = `Each row is one egg and time runs left to right. Strong colour means whole (red is whole but flipped), pale means scrambled. Golden eggs are outlined and the white line is when you served. Measured with otoc-echo-v1 on Moth Atlas (aer emulator), job ${run.job_id}.`;
  show("s-result");
  const sci = $<HTMLDetailsElement>("r-sci");
  const r = run;
  const draw = () => sci.open && drawHeatmap($<HTMLCanvasElement>("r-heat"), r, { t: v.t, highlight: targets(l, r) });
  sci.ontoggle = draw;
  requestAnimationFrame(draw);
  const next = $<HTMLButtonElement>("r-next");
  next.textContent = state.over ? "See results" : v.win ? "Next level" : "Try again";
  next.onclick = () => {
    sfx.click();
    if (state.over) showEnd();
    else showChoose();
  };
}

function showEnd() {
  const best = Math.max(state.score, +(localStorage.getItem(BEST_KEY) ?? 0));
  localStorage.setItem(BEST_KEY, String(best));
  $("e-title").textContent = state.cleared ? "ALL EGGS SERVED" : "OUT OF EGGS";
  $("e-score").textContent = `${state.score} pts · best ${best}`;
  const perfects = state.history.filter((h) => h.outcome === "perfect").length;
  $("e-text").textContent = state.cleared
    ? `You cleared all ${LEVELS.length} pans${perfects ? ` with ${perfects} perfect serve${perfects > 1 ? "s" : ""}` : ""}. Along the way you outran a spreading crack, used a Clifford lid to stop scrambling outright and caught an echo bouncing back off the pan's edge. All three are real behaviours of qubits, measured on Moth Atlas.`
    : `You reached level ${state.level + 1}. Scrambling is fast. The trick is to see where the crack is heading before it gets there.`;
  $("e-eggs").innerHTML = state.history
    .map((h) => `<img src="${spriteUrl(h.outcome === "perfect" ? "egg_fresh" : h.win ? "egg_crack" : h.outcome === "burnt" ? "egg_burnt" : "egg_scrambled")}" alt="${h.outcome}" title="${STAMP[h.outcome]} t=${h.t.toFixed(1)}" />`)
    .join("");
  show("s-end");
}

function startGame() {
  sfx.unlock();
  sfx.click();
  state = newRun();
  showChoose();
}

/* ---------------- boot ---------------- */
async function main() {
  const [g, f] = await Promise.all([loadGrid(), loadFeatured(), loadSpriteImages()]);
  runs = [...f, ...g.runs]; // headline runs (also used in the video) win ties
  const best = localStorage.getItem(BEST_KEY);
  if (best) $("best").textContent = `Best score: ${best}`;
  $("start").addEventListener("click", startGame);
  $("e-again").addEventListener("click", startGame);
  $("serve").addEventListener("click", serve);
  pan.addEventListener("pointerdown", serve);
  window.addEventListener("keydown", (e) => {
    if ((e.code === "Space" || e.code === "Enter") && cooking) {
      e.preventDefault();
      serve();
    }
  });
  const mute = $<HTMLButtonElement>("mute");
  mute.addEventListener("click", () => {
    sfx.setMuted(!sfx.muted);
    mute.textContent = sfx.muted ? "Sound off" : "Sound on";
  });
  initLive();
}

main().catch((e) => {
  $("s-title").insertAdjacentHTML("beforeend", `<p class="status err">Failed to load: ${(e as Error).message}</p>`);
});
