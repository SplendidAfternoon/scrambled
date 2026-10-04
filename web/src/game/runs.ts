import type { Run } from "../lib/otoc";
import type { PanChoice } from "./rules";

/** The measured run backing a pan choice (exact parameter match). */
export function findRun(runs: Run[], c: PanChoice): Run | undefined {
  return runs.find(
    (r) =>
      r.params.n_sites === c.n_sites &&
      Math.abs(r.params.theta_x_pi - c.theta_x_pi) < 0.005 &&
      Math.abs(r.params.theta_zz_pi - c.theta_zz_pi) < 0.005 &&
      r.params.depth === 32,
  );
}
