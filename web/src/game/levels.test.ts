import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { Grid, Run } from "../lib/otoc";
import { LEVELS } from "./levels";
import { winningSteps } from "./rules";
import { findRun } from "./runs";

const data = (f: string) => JSON.parse(readFileSync(resolve(__dirname, "../../public/data", f), "utf-8"));
const grid: Grid = data("grid.json");
const featured: Run[] = data("featured.json");
const runs = [...featured, ...grid.runs];

describe("levels against the measured data", () => {
  for (const level of LEVELS) {
    it(`level ${level.id} "${level.title}" has a measured run for every pan and is solvable`, () => {
      const windows = level.choices.map((c) => {
        const run = findRun(runs, c);
        expect(run, `${c.label} missing from data`).toBeTruthy();
        return winningSteps(level, run!);
      });
      console.log(`L${level.id}`, level.choices.map((c, i) => `${c.label}: [${windows[i].join(",")}]`).join(" | "));
      expect(windows.some((w) => w.length >= 1)).toBe(true);
    });
  }
  it("choice levels have at least one losing pan (the choice matters)", () => {
    for (const level of LEVELS.filter((l) => l.choices.length > 1)) {
      const sizes = level.choices.map((c) => winningSteps(level, findRun(runs, c)!).length);
      expect(Math.min(...sizes), `level ${level.id}`).toBeLessThan(Math.max(...sizes));
    }
  });
});
