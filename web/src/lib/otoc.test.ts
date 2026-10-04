import { describe, expect, it } from "vitest";
import { absFat, arrival, cooked, Fat, fromAtlasResult, meanAbs, nearestRun, offKickMean, snapClifford, type Grid, type Run } from "./otoc";

const run = (F_re: number[][], over: Partial<Run> = {}): Run => ({
  job_id: "j",
  engine_id: "otoc-echo-v1",
  params: { n_sites: F_re.length, depth: F_re[0].length, theta_x_pi: 0.3, theta_zz_pi: 0.35 },
  kick_site: 1,
  backend: "aer",
  F_re,
  F_im: null,
  light_cone: F_re.map((row, s) => row.map((_, i) => (i + 1 >= Math.abs(s - 1) + 1 ? 1 : 0))),
  ...over,
});

const r = run([
  [1, 1, 0.5, 0],
  [-1, -0.5, 0, 0.5],
  [1, 1, 1, 0.2],
]);

describe("Fat", () => {
  it("returns integer steps exactly and interpolates between them", () => {
    expect(Fat(r, 0, 3)).toEqual([0.5, 0]);
    expect(Fat(r, 0, 2.5)[0]).toBeCloseTo(0.75);
  });
  it("clamps t outside [1, depth]", () => {
    expect(Fat(r, 1, 0)[0]).toBe(-1);
    expect(Fat(r, 1, 99)[0]).toBe(0.5);
  });
  it("uses the imaginary part for |F|", () => {
    const c = run([[0.6, 0.6]], { F_im: [[0.8, 0]], kick_site: 0 });
    expect(absFat(c, 0, 1)).toBeCloseTo(1);
  });
});

describe("summaries", () => {
  it("meanAbs averages |F| over the given sites", () => {
    expect(meanAbs(r, [0, 1], 1)).toBe(1);
    expect(meanAbs(r, [], 1)).toBe(0);
  });
  it("offKickMean skips the kicked site", () => {
    expect(offKickMean(r)).toEqual([1, 1, 0.75, 0.1]);
  });
  it("arrival reads the light cone", () => {
    expect(arrival(r)).toEqual([2, 1, 2]);
    expect(arrival(run([[1, 1]], { light_cone: [[0, 0]] }))).toEqual([null]);
  });
});

describe("cooked", () => {
  it("is zero at t=1 and while |F| stays 1", () => {
    expect(cooked(r, 2, 1)).toBe(0);
    expect(cooked(r, 2, 3)).toBe(0);
  });
  it("grows monotonically as |F| decays and clips to 1", () => {
    const a = cooked(r, 0, 3);
    const b = cooked(r, 0, 4);
    expect(a).toBeGreaterThan(0);
    expect(b).toBeGreaterThan(a);
    expect(cooked(run([[0, 0, 0, 0]], { kick_site: 0 }), 0, 4, 10)).toBe(1);
  });
  it("matches the trapezoid integral", () => {
    // site 0: g = [0,0,0.5,1]; integral 1..4 = 0 + 0.25 + 0.75 = 1.0; *1.45/3
    expect(cooked(r, 0, 4)).toBeCloseTo(1.45 / 3);
  });
});

describe("nearestRun", () => {
  const mk = (n: number, tx: number, tzz: number) => run([[1]], { params: { n_sites: n, depth: 1, theta_x_pi: tx, theta_zz_pi: tzz }, job_id: `${n}-${tx}-${tzz}` });
  const grid: Grid = { engine_id: "otoc-echo-v1", axes: { n_sites: [8, 12], theta_x_pi: [], theta_zz_pi: [] }, depth: 1, runs: [mk(8, 0.1, 0.25), mk(8, 0.3, 1), mk(12, 0.3, 0.35)] };
  it("prefers the closest n_sites, then the closest angles", () => {
    expect(nearestRun(grid, 8, 0.28, 0.9).job_id).toBe("8-0.3-1");
    expect(nearestRun(grid, 11, 0.1, 0.25).job_id).toBe("12-0.3-0.35");
  });
});

describe("fromAtlasResult", () => {
  const body = {
    result: {
      output: {
        data: { series: { F_re: [[1, 0.5], [-1, -1]], F_im: [[0, 0], [0, 0]] } },
        extras: { kick_site: 1, light_cone: [[0, 1], [1, 1]], summary: { live: 4 } },
        provenance: { backend: "aer" },
      },
    },
  };
  it("parses the documented envelope", () => {
    const p = fromAtlasResult(body, "abc", { theta_x: Math.PI * 0.3, theta_zz: Math.PI });
    expect(p.params).toEqual({ n_sites: 2, depth: 2, theta_x_pi: 0.3, theta_zz_pi: 1 });
    expect(p.F_im).toBeNull();
    expect(p.kick_site).toBe(1);
    expect(p.backend).toBe("aer");
  });
  it("accepts the bare output shape and rejects garbage", () => {
    expect(fromAtlasResult(body.result.output, "x", { theta_x: 1, theta_zz: 1 }).job_id).toBe("x");
    expect(() => fromAtlasResult({ nope: 1 }, "x", {})).toThrow();
  });
});

it("snapClifford snaps near pi only", () => {
  expect(snapClifford(0.98)).toBe(1);
  expect(snapClifford(0.9)).toBe(0.9);
});
