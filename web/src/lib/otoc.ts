/** Measured otoc-echo-v1 runs: types, parsing and the pure maths the UI draws from. */

export interface RunParams {
  n_sites: number;
  depth: number;
  theta_x_pi: number;
  theta_zz_pi: number;
}

export interface Run {
  label?: string | null;
  job_id: string;
  engine_id: string;
  params: RunParams;
  kick_site: number;
  backend: string;
  /** F_re[site][t-1] */
  F_re: number[][];
  F_im: number[][] | null;
  /** light_cone[site][t-1] = 1 once the perturbation has reached the site */
  light_cone: number[][];
  summary?: Record<string, number>;
}

export interface Grid {
  engine_id: string;
  axes: { n_sites: number[]; theta_x_pi: number[]; theta_zz_pi: number[] };
  depth: number;
  runs: Run[];
}

export const sites = (run: Run) => run.F_re.length;
export const depth = (run: Run) => run.F_re[0]?.length ?? 0;

/** Complex F at integer step t (1-based). */
export function F(run: Run, site: number, t: number): [number, number] {
  return [run.F_re[site][t - 1], run.F_im ? run.F_im[site][t - 1] : 0];
}

/** F linearly interpolated along continuous t in [1, depth]. */
export function Fat(run: Run, site: number, t: number): [number, number] {
  const d = depth(run);
  const tc = Math.min(Math.max(t, 1), d);
  const i = Math.min(Math.floor(tc), d - 1 || 1);
  const f = d === 1 ? 0 : tc - i;
  const [a, b] = F(run, site, i);
  if (d === 1) return [a, b];
  const [c, e] = F(run, site, i + 1);
  return [a * (1 - f) + c * f, b * (1 - f) + e * f];
}

export const absFat = (run: Run, site: number, t: number) => Math.hypot(...Fat(run, site, t));

export function meanAbs(run: Run, siteList: number[], t: number): number {
  if (!siteList.length) return 0;
  return siteList.reduce((s, k) => s + absFat(run, k, t), 0) / siteList.length;
}

/** First step at which the light cone reaches each site (null if never within depth). */
export function arrival(run: Run): (number | null)[] {
  return run.light_cone.map((row) => {
    const i = row.findIndex((v) => v > 0);
    return i < 0 ? null : i + 1;
  });
}

/** Mean |F| over every site except the kicked one, per integer step. */
export function offKickMean(run: Run): number[] {
  const others = [...Array(sites(run)).keys()].filter((k) => k !== run.kick_site);
  return Array.from({ length: depth(run) }, (_, i) => meanAbs(run, others, i + 1));
}

/**
 * Accumulated "cooking" per site at continuous t: 1.45/(depth-1) * integral_1^t (1 - |F|) dtau, clipped to [0, 1].
 * Same accumulator compose.py uses for the video, as a pure function of t.
 */
export function cooked(run: Run, site: number, t: number, gain = 1.45): number {
  const d = depth(run);
  if (d < 2) return 0;
  const tc = Math.min(Math.max(t, 1), d);
  let acc = 0;
  const g = (x: number) => 1 - absFat(run, site, x);
  let x = 1;
  while (x + 1 <= tc) {
    acc += (g(x) + g(x + 1)) / 2;
    x += 1;
  }
  if (tc > x) acc += ((g(x) + g(tc)) / 2) * (tc - x);
  return Math.min(1, Math.max(0, (acc * gain) / (d - 1)));
}

/** Nearest measured run on the grid (n_sites exact if available, then nearest angles). */
export function nearestRun(grid: Grid, n: number, txPi: number, tzzPi: number): Run {
  const ns = grid.runs.map((r) => r.params.n_sites);
  const nBest = ns.reduce((b, v) => (Math.abs(v - n) < Math.abs(b - n) ? v : b), ns[0]);
  let best = grid.runs[0];
  let bestD = Infinity;
  for (const r of grid.runs) {
    if (r.params.n_sites !== nBest) continue;
    const d = (r.params.theta_x_pi - txPi) ** 2 + (r.params.theta_zz_pi - tzzPi) ** 2;
    if (d < bestD) {
      bestD = d;
      best = r;
    }
  }
  return best;
}

/** Parse an Atlas /jobs/{id}/result body for otoc-echo-v1 (accepts the looser documented shapes). */
export function fromAtlasResult(body: unknown, jobId: string, params: Record<string, unknown>): Run {
  const b = body as Record<string, any>;
  let env = b?.result ?? b;
  env = env?.output ?? env;
  const series = env?.data?.series;
  const extras = env?.extras;
  if (!series?.F_re || !extras) throw new Error("Unexpected otoc-echo-v1 result shape");
  const F_im: number[][] = series.F_im ?? null;
  const real = !F_im || F_im.every((row) => row.every((v) => Math.abs(v) < 1e-9));
  const n = series.F_re.length;
  const d = series.F_re[0].length;
  return {
    job_id: jobId,
    engine_id: "otoc-echo-v1",
    params: {
      n_sites: n,
      depth: d,
      theta_x_pi: Number(params.theta_x) / Math.PI,
      theta_zz_pi: Number(params.theta_zz) / Math.PI,
    },
    kick_site: extras.kick_site,
    backend: env?.provenance?.backend ?? "unknown",
    F_re: series.F_re,
    F_im: real ? null : F_im,
    light_cone: extras.light_cone ?? series.F_re.map((row: number[]) => row.map(() => 1)),
    summary: extras.summary,
  };
}

/** theta_zz slider value snapped to pi (the Clifford point) when close. */
export const snapClifford = (tzzPi: number, tol = 0.03) => (Math.abs(tzzPi - 1) <= tol ? 1 : tzzPi);
