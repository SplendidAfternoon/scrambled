/** Canvas drawing shared by the explorer and the game: RdBu heatmap of F, light cone, line plot. */
import { arrival, depth, sites, type Run } from "./otoc";

const RDBU: [number, number, number][] = [
  [103, 0, 31], [178, 24, 43], [214, 96, 77], [244, 165, 130], [253, 219, 199],
  [247, 247, 247], [209, 229, 240], [146, 197, 222], [67, 147, 195], [33, 102, 172], [5, 48, 97],
];

/** Matplotlib RdBu: -1 -> red, 0 -> white, +1 -> blue. */
export function rdbu(v: number): [number, number, number] {
  const x = (Math.min(1, Math.max(-1, v)) + 1) / 2 * (RDBU.length - 1);
  const i = Math.min(Math.floor(x), RDBU.length - 2);
  const f = x - i;
  const a = RDBU[i];
  const b = RDBU[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

export function fitCanvas(c: HTMLCanvasElement): CanvasRenderingContext2D {
  const dpr = Math.min(window.devicePixelRatio || 1, 2);
  const w = Math.max(1, Math.round(c.clientWidth * dpr));
  const h = Math.max(1, Math.round(c.clientHeight * dpr));
  if (c.width !== w || c.height !== h) {
    c.width = w;
    c.height = h;
  }
  const ctx = c.getContext("2d")!;
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  return ctx;
}

export interface HeatOpts {
  t?: number;
  /** only reveal columns up to t (game) */
  reveal?: boolean;
  highlight?: number[];
  showCone?: boolean;
}

/** Heatmap of Re F: x = echo step t, y = site (qubit). */
export function drawHeatmap(c: HTMLCanvasElement, run: Run, o: HeatOpts = {}) {
  const ctx = fitCanvas(c);
  const W = c.width;
  const H = c.height;
  const n = sites(run);
  const d = depth(run);
  const cw = W / d;
  const ch = H / n;
  ctx.fillStyle = "#14110f";
  ctx.fillRect(0, 0, W, H);
  for (let s = 0; s < n; s++) {
    for (let i = 0; i < d; i++) {
      if (o.reveal && o.t !== undefined && i + 1 > Math.floor(o.t)) continue;
      const [r, g, b] = rdbu(run.F_re[s][i]);
      ctx.fillStyle = `rgb(${r | 0},${g | 0},${b | 0})`;
      ctx.fillRect(Math.floor(i * cw), Math.floor(s * ch), Math.ceil(cw) + 1, Math.ceil(ch) + 1);
    }
  }
  if (o.showCone !== false) {
    const arr = arrival(run);
    ctx.strokeStyle = "rgba(255, 196, 0, 0.95)";
    ctx.lineWidth = Math.max(1.5, W / 400);
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    arr.forEach((a, s) => {
      const x = a === null ? W : (a - 1) * cw;
      const y0 = s * ch;
      if (s === 0) ctx.moveTo(x, y0);
      else ctx.lineTo(x, y0);
      ctx.lineTo(x, y0 + ch);
    });
    ctx.stroke();
    ctx.setLineDash([]);
  }
  for (const s of o.highlight ?? []) {
    ctx.strokeStyle = "#ffd54a";
    ctx.lineWidth = Math.max(2, W / 300);
    ctx.strokeRect(1, s * ch + 1, W - 2, ch - 2);
  }
  ctx.fillStyle = "rgba(0,0,0,0.55)";
  ctx.fillRect(0, run.kick_site * ch, Math.max(4, W / 120), ch);
  if (o.t !== undefined) {
    const x = ((o.t - 0.5) / d) * W;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = Math.max(2, W / 350);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
}

/** Line plot of one or more series over t = 1..d, y in [0, 1]. */
export function drawLines(c: HTMLCanvasElement, series: { values: number[]; color: string; label: string }[], t?: number, threshold?: number) {
  const ctx = fitCanvas(c);
  const W = c.width;
  const H = c.height;
  const pad = Math.round(H * 0.08);
  ctx.fillStyle = "#14110f";
  ctx.fillRect(0, 0, W, H);
  ctx.strokeStyle = "rgba(255,255,255,0.12)";
  ctx.lineWidth = 1;
  for (const y of [0, 0.5, 1]) {
    const yy = H - pad - y * (H - 2 * pad);
    ctx.beginPath();
    ctx.moveTo(0, yy);
    ctx.lineTo(W, yy);
    ctx.stroke();
  }
  if (threshold !== undefined) {
    const yy = H - pad - threshold * (H - 2 * pad);
    ctx.strokeStyle = "rgba(255, 213, 74, 0.8)";
    ctx.setLineDash([6, 5]);
    ctx.beginPath();
    ctx.moveTo(0, yy);
    ctx.lineTo(W, yy);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  const dpr = W / Math.max(1, c.clientWidth);
  for (const s of series) {
    const d = s.values.length;
    ctx.strokeStyle = s.color;
    ctx.lineWidth = 2 * dpr;
    ctx.beginPath();
    s.values.forEach((v, i) => {
      const x = (i / Math.max(1, d - 1)) * W;
      const y = H - pad - Math.min(1, Math.max(0, v)) * (H - 2 * pad);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  if (t !== undefined && series[0]) {
    const d = series[0].values.length;
    const x = ((t - 1) / Math.max(1, d - 1)) * W;
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 1.5 * dpr;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, H);
    ctx.stroke();
  }
}
