import type { Level, PanChoice } from "./rules";

const GENTLE: PanChoice = { label: "Low heat", hint: "θx = 0.1π: a gentle transverse kick. The nudge spreads slowly.", n_sites: 12, theta_x_pi: 0.1, theta_zz_pi: 0.35 };
const HOT: PanChoice = { label: "High heat", hint: "θx = 0.3π, θzz = 0.35π: strong scrambling. Fast, messy, irreversible-looking.", n_sites: 12, theta_x_pi: 0.3, theta_zz_pi: 0.35 };
const STIR: PanChoice = { label: "Sparse stir", hint: "θzz = 0.25π: the sparse coupling. Scrambles hard, then the echo bounces back off the pan's edges.", n_sites: 12, theta_x_pi: 0.3, theta_zz_pi: 0.25 };
const LID: PanChoice = { label: "Clifford lid", hint: "θzz = π: every gate is a Clifford. Operators stay single Pauli strings, so nothing can scramble.", n_sites: 12, theta_x_pi: 0.3, theta_zz_pi: 1 };

/**
 * Each level is backed by runs measured on Atlas (otoc-echo-v1, aer, exact, 12 qubits, depth 32).
 * Targets are offsets from the kicked egg (the centre). The windows are checked against the shipped data in levels.test.ts.
 */
export const LEVELS: Level[] = [
  {
    id: 1,
    title: "Crack one egg",
    blurb: "One qubit in the middle of the pan gets nudged. Keep the two golden eggs at the edges whole. The nudge spreads outward, so serve before it reaches them, but not before the cook bar turns green.",
    targetOffsets: [5, -6],
    minT: 4,
    threshold: 0.8,
    seconds: 14,
    choices: [GENTLE],
  },
  {
    id: 2,
    title: "Mind the light cone",
    blurb: "The golden eggs sit three and four places from the crack. Pick your heat. The light cone (dashed line) shows how fast the nudge travels.",
    targetOffsets: [3, 4],
    minT: 8,
    threshold: 0.7,
    seconds: 12,
    choices: [HOT, GENTLE],
  },
  {
    id: 3,
    title: "Put a lid on it",
    blurb: "The golden eggs are right next to the crack and they have to cook for a long time. No heat setting survives that. You need a circuit that cannot scramble.",
    targetOffsets: [-1, 1, 2],
    minT: 20,
    threshold: 0.9,
    seconds: 11,
    choices: [HOT, STIR, LID],
  },
  {
    id: 4,
    title: "Catch the echo",
    blurb: "No lid this time. The sparse stir scrambles everything, then the echo bounces back off the edges of the pan. Serve while the golden eggs are whole again.",
    targetOffsets: [3, 4, 5],
    minT: 12,
    threshold: 0.82,
    seconds: 11,
    choices: [STIR],
  },
  {
    id: 5,
    title: "Hot pan, long cook",
    blurb: "Edge eggs, long cook, fast clock. One pan gives you a wide window and one gives you almost none. Choose, then time it.",
    targetOffsets: [5, -6],
    minT: 15,
    threshold: 0.85,
    seconds: 8,
    choices: [GENTLE, HOT, STIR],
  },
];
