/** DON'T SCRAMBLE THE EGG: pure game rules (no DOM), driven by measured otoc-echo-v1 runs. */
import { absFat, meanAbs, type Run } from "../lib/otoc";

export interface PanChoice {
  label: string;
  hint: string;
  n_sites: number;
  theta_x_pi: number;
  theta_zz_pi: number;
}

export interface Level {
  id: number;
  title: string;
  blurb: string;
  /** egg sites the player must keep readable, given as offsets from the kicked site */
  targetOffsets: number[];
  /** must cook at least this many echo steps */
  minT: number;
  /** mean |F| over target sites needed to serve a whole egg */
  threshold: number;
  /** seconds for the full 32-step cook to play out */
  seconds: number;
  choices: PanChoice[];
}

export type Outcome = "raw" | "scrambled" | "served" | "perfect" | "burnt";

export interface Verdict {
  outcome: Outcome;
  t: number;
  memory: number;
  score: number;
  win: boolean;
}

export function targets(level: Level, run: Run): number[] {
  const n = run.F_re.length;
  return level.targetOffsets.map((o) => run.kick_site + o).filter((s) => s >= 0 && s < n);
}

/** Judge a SERVE at continuous echo step t. */
export function judge(level: Level, run: Run, t: number): Verdict {
  const depth = run.F_re[0].length;
  const ts = targets(level, run);
  const memory = meanAbs(run, ts, t);
  if (t >= depth) return { outcome: "burnt", t, memory, score: 0, win: false };
  if (t < level.minT) return { outcome: "raw", t, memory, score: 0, win: false };
  if (memory < level.threshold) return { outcome: "scrambled", t, memory, score: 0, win: false };
  const allWhole = ts.every((s) => absFat(run, s, t) >= level.threshold);
  const perfect = allWhole && memory >= Math.max(level.threshold, 0.9);
  const score = Math.round(1000 * memory) + Math.round(25 * (t - level.minT)) + (perfect ? 500 : allWhole ? 150 : 0);
  return { outcome: perfect ? "perfect" : "served", t, memory, score, win: true };
}

/** Steps (integer t >= minT) at which serving wins: the level's "window". Used for hints and to test solvability. */
export function winningSteps(level: Level, run: Run): number[] {
  const d = run.F_re[0].length;
  const out: number[] = [];
  for (let t = Math.ceil(level.minT); t < d; t++) if (judge(level, run, t).win) out.push(t);
  return out;
}

/** Egg sprite state for one site at step t. */
export type EggState = "fresh" | "crack" | "cook" | "scrambled";
export function eggState(absF: number): EggState {
  if (absF >= 0.85) return "fresh";
  if (absF >= 0.6) return "crack";
  if (absF >= 0.35) return "cook";
  return "scrambled";
}

export interface RunState {
  level: number;
  lives: number;
  score: number;
  history: Verdict[];
}

export const newRun = (lives = 3): RunState => ({ level: 0, lives, score: 0, history: [] });

/** Apply a verdict: wins advance, losses cost a life and retry the level. */
export function advance(state: RunState, v: Verdict, levelCount: number): RunState & { over: boolean; cleared: boolean } {
  const history = [...state.history, v];
  if (v.win) {
    const level = state.level + 1;
    return { ...state, level, score: state.score + v.score, history, over: level >= levelCount, cleared: level >= levelCount };
  }
  const lives = state.lives - 1;
  return { ...state, lives, history, over: lives <= 0, cleared: false };
}
