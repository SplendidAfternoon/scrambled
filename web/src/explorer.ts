import { AtlasError, keyStore, measureOtoc, otocParams, pickRoute, serverHealth, type ServerHealth } from "./lib/atlas";
import { fmtPi, loadFeatured, loadGrid, loadLadderIndex, loadLiveRecorded, shortId, type RecordedRun } from "./lib/data";
import { drawHeatmap, drawLines } from "./lib/draw";
import { drawStrips, loadLadder, type LoadedLadder } from "./lib/eggstrip";
import { absFat, arrival, depth, nearestRun, offKickMean, sites, snapClifford, type Grid, type Run } from "./lib/otoc";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;

const ui = {
  tx: $<HTMLInputElement>("tx"),
  txVal: $("tx-val"),
  tzz: $<HTMLInputElement>("tzz"),
  tzzVal: $("tzz-val"),
  nSeg: $("n-seg"),
  nVal: $("n-val"),
  key: $<HTMLInputElement>("key"),
  remember: $<HTMLInputElement>("remember"),
  measure: $<HTMLButtonElement>("measure"),
  cancel: $<HTMLButtonElement>("cancel"),
  status: $("status"),
  modeTag: $("mode-tag"),
  routeHost: $("route-host"),
  photo: $<HTMLCanvasElement>("photo"),
  ticks: $("ticks"),
  t: $<HTMLInputElement>("t"),
  tVal: $("t-val"),
  play: $<HTMLButtonElement>("play"),
  heat: $<HTMLCanvasElement>("heat"),
  lines: $<HTMLCanvasElement>("lines"),
  prov: $("prov"),
  lent: $("lent"),
  recorded: $("recorded"),
  recordedText: $("recorded-text"),
  recordedBtn: $<HTMLButtonElement>("recorded-btn"),
  ownKey: $<HTMLDetailsElement>("own-key"),
};

const route = pickRoute(location);
ui.routeHost.textContent = route === "direct" ? "api.mothquantum.com" : "api.mothquantum.com (via this site's /api/atlas proxy)";

let grid: Grid;
let ladder: LoadedLadder;
let run: Run;
let live: Run[] = [];
let recorded: RecordedRun[] = [];
let health: ServerHealth | null = null;
let n = 12;
let playing = false;
let abort: AbortController | null = null;

const txPi = () => +ui.tx.value;
const tzzPi = () => snapClifford(+ui.tzz.value);

function status(msg: string, err = false) {
  ui.status.textContent = msg;
  ui.status.classList.toggle("err", err);
}

function sameParams(r: Run) {
  const p = r.params;
  return p.n_sites === n && Math.abs(p.theta_x_pi - txPi()) < 0.005 && Math.abs(p.theta_zz_pi - tzzPi()) < 0.005;
}

function pickRun(): { run: Run; exact: boolean; live: boolean; rec?: RecordedRun } {
  const l = live.find(sameParams);
  if (l) return { run: l, exact: true, live: true };
  const rec = recorded.find(sameParams);
  if (rec) return { run: rec, exact: true, live: false, rec };
  const r = nearestRun(grid, n, txPi(), tzzPi());
  return { run: r, exact: sameParams(r), live: false };
}

const lending = () => !ui.key.value.trim() && !!health?.server_key;

function syncMeasure() {
  const q = health?.remaining;
  if (lending() && q) {
    const left = Math.min(q.ip_hour, q.today);
    ui.measure.textContent = left > 0 ? `Measure on Atlas (${left} left)` : "Lent runs used up";
    ui.measure.disabled = left <= 0 || !!abort;
    ui.lent.hidden = false;
    ui.lent.textContent =
      `No key needed: the site lends its own. ${q.ip_hour} of ${health!.limits?.per_ip_hourly ?? "?"} runs left for you this hour, ` +
      `${q.today} of ${health!.limits?.daily ?? "?"} left today across all visitors.`;
  } else {
    ui.measure.textContent = "Measure on Atlas";
    ui.measure.disabled = !!abort;
    ui.lent.hidden = true;
  }
}

async function refreshHealth() {
  health = await serverHealth();
  if (!health?.server_key || ui.key.value) ui.ownKey.open = true;
  syncMeasure();
}

function showRecorded(rec: RecordedRun) {
  n = rec.params.n_sites;
  ui.tx.value = String(rec.params.theta_x_pi);
  ui.tzz.value = String(rec.params.theta_zz_pi);
  ui.t.value = "1";
  setRun();
  setPlaying(true);
}

function setupRecorded() {
  const rec = recorded[0];
  if (!rec) return;
  const via = rec.route.startsWith("proxy") ? "through this site's proxy" : "straight from the browser";
  ui.recordedText.innerHTML =
    `Measured on Atlas ${via} at ${rec.submitted_at.replace("T", " ").replace("Z", " UTC")}: ` +
    `θ<sub>x</sub> = ${fmtPi(rec.params.theta_x_pi)}, θ<sub>zz</sub> = ${fmtPi(rec.params.theta_zz_pi)}, ${rec.params.n_sites} qubits, aer emulator. ` +
    `Job <span class="mono" title="${rec.job_id}">${shortId(rec.job_id)}</span>.`;
  ui.recorded.hidden = false;
}

function syncLabels() {
  ui.txVal.textContent = fmtPi(txPi());
  const z = tzzPi();
  ui.tzzVal.textContent = z === 1 ? "π (Clifford)" : fmtPi(z);
  if (z === 1 && +ui.tzz.value !== 1) ui.tzz.value = "1";
  ui.nVal.textContent = String(n);
  for (const b of ui.nSeg.querySelectorAll("button")) b.setAttribute("aria-pressed", String(+b.dataset.n! === n));
}

function setRun() {
  syncLabels();
  const pick = pickRun();
  run = pick.run;
  ui.t.max = String(depth(run));
  ui.modeTag.textContent = pick.live ? "live" : pick.rec ? "recorded live" : "cached";
  ui.modeTag.className = `tag ${pick.live || pick.rec ? "live" : "cached"}`;
  const p = run.params;
  const arr = arrival(run);
  const far = arr[0];
  const head = pick.live
    ? "Measured live just now"
    : pick.rec
      ? `Recorded live run (${pick.rec.submitted_at.replace("T", " ").replace("Z", " UTC")}, ${pick.rec.route.split(" ")[0]} route)`
      : pick.exact
        ? "Measured run"
        : "Nearest measured run";
  ui.prov.innerHTML = `
    <div><b>${head}</b>:
      θ<sub>x</sub> = ${fmtPi(p.theta_x_pi)}, θ<sub>zz</sub> = ${fmtPi(p.theta_zz_pi)}${p.theta_zz_pi === 1 ? " (Clifford)" : ""}, ${p.n_sites} qubits, depth ${p.depth}</div>
    <div>engine <span class="mono">${run.engine_id}</span> · backend <span class="mono">${run.backend}</span> (emulator, exact) · job <span class="mono" title="${run.job_id}">${shortId(run.job_id)}</span></div>
    <div>kicked qubit ${run.kick_site} · light cone reaches the far end at t = ${far ?? "never (within depth)"}</div>
    ${!pick.exact && !pick.live ? `<div class="muted">No run measured at exactly these settings. ${health?.server_key ? "Press" : "Paste a key and press"} <i>Measure on Atlas</i> to measure them.</div>` : ""}`;
  ui.ticks.style.gridTemplateColumns = `repeat(${sites(run)}, 1fr)`;
  ui.ticks.innerHTML = Array.from({ length: sites(run) }, (_, s) => `<span>${s === run.kick_site ? "◆" : s}</span>`).join("");
  render();
}

function render() {
  const t = +ui.t.value;
  ui.tVal.textContent = `t = ${t.toFixed(1)}`;
  if (ladder) {
    const ctx = ui.photo.getContext("2d")!;
    drawStrips(ctx, ui.photo.width, ladder, run, t);
  }
  drawHeatmap(ui.heat, run, { t });
  const far = run.kick_site >= sites(run) / 2 ? 0 : sites(run) - 1;
  drawLines(ui.lines, [
    { values: offKickMean(run), color: "#ffc93c", label: "mean" },
    { values: Array.from({ length: depth(run) }, (_, i) => absFat(run, far, i + 1)), color: "#4393c3", label: "far" },
  ], t);
}

let last = 0;
function tick(now: number) {
  if (!playing) return;
  const dt = last ? (now - last) / 1000 : 0;
  last = now;
  let t = +ui.t.value + dt * 2.6;
  if (t >= depth(run)) {
    t = depth(run);
    setPlaying(false);
  }
  ui.t.value = String(t);
  render();
  requestAnimationFrame(tick);
}

function setPlaying(p: boolean) {
  playing = p;
  ui.play.textContent = p ? "❚❚" : "▶";
  ui.play.setAttribute("aria-label", p ? "Pause" : "Play");
  if (p) {
    if (+ui.t.value >= depth(run)) ui.t.value = "1";
    last = 0;
    requestAnimationFrame(tick);
  }
}

async function measure() {
  const key = ui.key.value.trim();
  const lent = lending();
  if (!key && !lent) {
    ui.ownKey.open = true;
    status("Paste your Atlas API key first. Until then the explorer shows the measured runs.", true);
    return;
  }
  if (lent && n > (health?.limits?.n_sites ?? 12)) {
    ui.ownKey.open = true;
    status(`The lent key is limited to ${health?.limits?.n_sites ?? 12} qubits. Pick 8 or 12, or paste your own key.`, true);
    return;
  }
  keyStore.set(key, ui.remember.checked);
  const params = otocParams(n, 32, txPi(), tzzPi());
  abort = new AbortController();
  ui.measure.disabled = true;
  ui.cancel.hidden = false;
  status(`Submitting otoc-echo-v1${lent ? " with the site's demo key" : ""} …`);
  try {
    const r = await measureOtoc(params, {
      route: lent ? "proxy" : route,
      key,
      signal: abort.signal,
      timeoutMs: 600_000,
      onSubmitted: (s) => {
        if (s.remaining && health) health.remaining = s.remaining;
        syncMeasure();
      },
      onStatus: (s) => status(`job ${s.job_id ? shortId(s.job_id) : ""} · ${s.status} · ${(s.elapsed / 1000).toFixed(0)} s`),
    });
    live = [r, ...live.filter((x) => x.job_id !== r.job_id)];
    status(`Done: job ${r.job_id}${lent ? " (demo key)" : ""}`);
    ui.t.value = "1";
    setRun();
    setPlaying(true);
  } catch (e) {
    const err = e as AtlasError;
    status(err.message + (err.cors || err.status === 429 ? "\nShowing the measured runs instead." : ""), true);
    if (err.status === 429) void refreshHealth();
  } finally {
    ui.cancel.hidden = true;
    abort = null;
    syncMeasure();
  }
}

async function main() {
  ui.key.value = keyStore.get();
  ui.remember.checked = keyStore.remembered();
  void refreshHealth();
  const [g, featured, li, rec] = await Promise.all([loadGrid(), loadFeatured(), loadLadderIndex(), loadLiveRecorded().catch(() => [])]);
  // The two headline runs from the video are part of the browsable set too.
  const seen = new Set(g.runs.map((r) => r.job_id));
  g.runs.push(...featured.filter((r) => !seen.has(r.job_id)));
  grid = g;
  recorded = rec;
  bind();
  setupRecorded();
  setRun();
  ladder = await loadLadder(li);
  render();
  setPlaying(true);
}

function bind() {
  ui.tx.addEventListener("input", setRun);
  ui.tzz.addEventListener("input", setRun);
  ui.nSeg.addEventListener("click", (e) => {
    const b = (e.target as HTMLElement).closest("button");
    if (!b) return;
    n = +b.dataset.n!;
    setRun();
  });
  ui.t.addEventListener("input", () => {
    setPlaying(false);
    render();
  });
  ui.play.addEventListener("click", () => setPlaying(!playing));
  ui.measure.addEventListener("click", measure);
  ui.cancel.addEventListener("click", () => abort?.abort());
  ui.key.addEventListener("input", syncMeasure);
  ui.recordedBtn.addEventListener("click", () => recorded[0] && showRecorded(recorded[0]));
  window.addEventListener("resize", render);
}

main().catch((e) => status(`Failed to load data: ${(e as Error).message}`, true));
