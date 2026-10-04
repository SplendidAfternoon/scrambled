import { describe, expect, it } from "vitest";
import type { Run } from "../lib/otoc";
import { advance, eggState, judge, newRun, targets, winningSteps, type Level } from "./rules";

// 3 sites, kick at 1, 6 steps. Site 2 decays then revives.
const run: Run = {
  job_id: "j",
  engine_id: "otoc-echo-v1",
  params: { n_sites: 3, depth: 6, theta_x_pi: 0.3, theta_zz_pi: 0.35 },
  kick_site: 1,
  backend: "aer",
  F_re: [
    [1, 1, 0.9, 0.5, 0.2, 0.1],
    [-1, -0.8, -0.5, -0.3, -0.2, -0.1],
    [1, 1, 0.4, 0.2, 0.95, 0.3],
  ],
  F_im: null,
  light_cone: [[0, 1, 1, 1, 1, 1], [1, 1, 1, 1, 1, 1], [0, 1, 1, 1, 1, 1]],
};

const level: Level = { id: 1, title: "t", blurb: "", targetOffsets: [1], minT: 3, threshold: 0.8, seconds: 10, choices: [] };

describe("judge", () => {
  it("serving before minT is raw", () => expect(judge(level, run, 2).outcome).toBe("raw"));
  it("serving while scrambled loses", () => {
    const v = judge(level, run, 4);
    expect(v.outcome).toBe("scrambled");
    expect(v.win).toBe(false);
  });
  it("catching the revival wins with a time bonus", () => {
    const v = judge(level, run, 5);
    expect(v.win).toBe(true);
    expect(v.outcome).toBe("perfect");
    expect(v.score).toBe(950 + 50 + 500);
  });
  it("letting it run to the end burns", () => expect(judge(level, run, 6).outcome).toBe("burnt"));
  it("ignores target offsets that fall off the chain", () => {
    expect(targets({ ...level, targetOffsets: [1, 5, -9] }, run)).toEqual([2]);
  });
  it("winningSteps finds the window", () => expect(winningSteps(level, run)).toEqual([5]));
});

it("eggState thresholds", () => {
  expect([1, 0.7, 0.5, 0.1].map(eggState)).toEqual(["fresh", "crack", "cook", "scrambled"]);
});

describe("advance", () => {
  it("wins advance and add score; finishing all levels clears", () => {
    const s = advance(newRun(), judge(level, run, 5), 1);
    expect(s.cleared).toBe(true);
    expect(s.score).toBe(1500);
  });
  it("losses cost a life and end the run at zero", () => {
    let s = { ...newRun(2), over: false, cleared: false };
    s = advance(s, judge(level, run, 2), 3);
    expect(s.lives).toBe(1);
    expect(s.over).toBe(false);
    s = advance(s, judge(level, run, 4), 3);
    expect(s.over).toBe(true);
    expect(s.level).toBe(0);
  });
});
