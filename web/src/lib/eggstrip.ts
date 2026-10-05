/**
 * The egg photo, cut into one vertical strip per qubit. Each strip is drawn from pre-rendered Atlas image ladders:
 *  - while a site still "remembers" (low accumulated cooking), it slides along the blur-v1 ladder by 1 - |F|;
 *  - once cooked, it morphs along the telablur-v1 ladder from whole eggs (photo A) to scrambled eggs (photo B);
 *  - Re F < 0 (an inverted echo) flips the strip upside down.
 * Compositing here is classical (canvas drawImage), the ladders and F are from Atlas.
 */
import { absFat, cooked, Fat, sites, type Run } from "./otoc";

export interface Ladder {
  size: number;
  blur: { file: string; job_id: string | null; strength: number }[];
  tela: { file: string; job_id: string | null; strength: number }[];
  A: string;
  B: string;
}

export interface LoadedLadder {
  blur: HTMLImageElement[];
  tela: HTMLImageElement[];
}

const load = (src: string) =>
  new Promise<HTMLImageElement>((res, rej) => {
    const im = new Image();
    im.decoding = "async";
    im.onload = () => res(im);
    im.onerror = () => rej(new Error(`image failed: ${src}`));
    im.src = src;
  });

export async function loadLadder(l: Ladder): Promise<LoadedLadder> {
  const [blur, tela] = await Promise.all([Promise.all(l.blur.map((b) => load(b.file))), Promise.all(l.tela.map((b) => load(b.file)))]);
  return { blur, tela };
}

/** Index + crossfade fraction for position x in [0, 1] along a ladder of n images. */
export function ladderPos(n: number, x: number): [number, number] {
  const p = Math.min(1, Math.max(0, x)) * (n - 1);
  const i = Math.min(Math.floor(p), n - 2);
  return [i, p - i];
}

const COOK_START = 0.35;

/** Which ladder and where, for one site at t. Pure, for testing. */
export function stripLook(run: Run, site: number, t: number): { ladder: "blur" | "tela"; x: number; flip: boolean } {
  const mem = absFat(run, site, t);
  const c = cooked(run, site, t);
  const flip = Fat(run, site, t)[0] < 0;
  if (c < COOK_START) return { ladder: "blur", x: 1 - mem, flip };
  return { ladder: "tela", x: (c - COOK_START) / (1 - COOK_START), flip };
}

export function drawStrips(ctx: CanvasRenderingContext2D, size: number, L: LoadedLadder, run: Run, t: number) {
  const n = sites(run);
  ctx.clearRect(0, 0, size, size);
  for (let s = 0; s < n; s++) {
    const x0 = Math.round((s * size) / n);
    const x1 = Math.round(((s + 1) * size) / n);
    const look = stripLook(run, s, t);
    const stack = L[look.ladder];
    const [i, f] = ladderPos(stack.length, look.x);
    const sw = stack[i].naturalWidth;
    const sx0 = (x0 / size) * sw;
    const sx1 = (x1 / size) * sw;
    ctx.save();
    ctx.beginPath();
    ctx.rect(x0, 0, x1 - x0, size);
    ctx.clip();
    if (look.flip) {
      ctx.translate(0, size);
      ctx.scale(1, -1);
    }
    ctx.globalAlpha = 1;
    ctx.drawImage(stack[i], sx0, 0, sx1 - sx0, sw, x0, 0, x1 - x0, size);
    if (f > 0.001) {
      ctx.globalAlpha = f;
      ctx.drawImage(stack[i + 1], sx0, 0, sx1 - sx0, sw, x0, 0, x1 - x0, size);
    }
    ctx.restore();
  }
  ctx.globalAlpha = 1;
}
