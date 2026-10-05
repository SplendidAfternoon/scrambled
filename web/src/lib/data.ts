import type { Ladder } from "./eggstrip";
import type { Grid, Run } from "./otoc";

async function json<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

export const loadGrid = () => json<Grid>("data/grid.json");
export const loadFeatured = () => json<Run[]>("data/featured.json");
export const loadLadderIndex = () => json<Ladder>("data/ladder.json");

/** Real browser-initiated Atlas runs captured from this explorer (direct and via the proxy). */
export interface RecordedRun extends Run {
  submitted_at: string;
  updated_at: string;
  route: string;
  screenshot?: string;
}
export const loadLiveRecorded = () => json<RecordedRun[]>("data/live_recorded.json");


export const fmtPi = (x: number) => (x === 1 ? "π" : `${+x.toFixed(3)}π`);
export const shortId = (id: string) => id.slice(0, 8);
