import { expect, it } from "vitest";
import type { Run } from "./otoc";
import { ladderPos, stripLook } from "./eggstrip";

const run: Run = {
  job_id: "j", engine_id: "otoc-echo-v1", backend: "aer", kick_site: 1, F_im: null,
  params: { n_sites: 3, depth: 4, theta_x_pi: 0.3, theta_zz_pi: 0.35 },
  F_re: [[1, 1, 1, 1], [-1, -1, -1, -1], [1, 0, 0, 0]],
  light_cone: [[1, 1, 1, 1], [1, 1, 1, 1], [1, 1, 1, 1]],
};

it("ladderPos crossfades between neighbours and clamps", () => {
  expect(ladderPos(5, 0)).toEqual([0, 0]);
  expect(ladderPos(5, 1)).toEqual([3, 1]);
  expect(ladderPos(5, 0.5)).toEqual([2, 0]);
  expect(ladderPos(5, 2)).toEqual([3, 1]);
});

it("a remembering site stays sharp, an inverted one flips, a cooked one moves to the scrambled ladder", () => {
  expect(stripLook(run, 0, 4)).toEqual({ ladder: "blur", x: 0, flip: false });
  expect(stripLook(run, 1, 2).flip).toBe(true);
  expect(stripLook(run, 2, 1.5).ladder).toBe("blur");
  const late = stripLook(run, 2, 4);
  expect(late.ladder).toBe("tela");
  expect(late.x).toBeGreaterThan(0.5);
});
