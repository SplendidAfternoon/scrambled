import type { Level, PanChoice } from "./rules";

const GENTLE: PanChoice = { label: "Low heat", hint: "Gentle. The crack creeps outward slowly, so eggs near it stay whole for a while.", flames: 1, n_sites: 12, theta_x_pi: 0.1, theta_zz_pi: 0.35 };
const HOT: PanChoice = { label: "High heat", hint: "Fierce. The crack races through the pan and the eggs it reaches stay scrambled.", flames: 3, n_sites: 12, theta_x_pi: 0.3, theta_zz_pi: 0.35 };
const STIR: PanChoice = { label: "Sparse stir", hint: "Scrambles everything fast. Then the ripple bounces off the pan's edge and the eggs pull back together for a moment.", flames: 2, n_sites: 12, theta_x_pi: 0.3, theta_zz_pi: 0.25 };
const LID: PanChoice = { label: "Clifford lid", hint: "A special lid. Under it the crack moves around but nothing ever scrambles, however long you cook.", flames: 0, n_sites: 12, theta_x_pi: 0.3, theta_zz_pi: 1 };

/**
 * Each level is backed by runs measured on Atlas (otoc-echo-v1, aer, exact, 12 qubits, depth 32).
 * Targets are offsets from the kicked egg (the centre). The windows are checked against the shipped data in levels.test.ts.
 */
export const LEVELS: Level[] = [
  {
    id: 1,
    title: "Crack one egg",
    blurb: "The egg with the red ring gets cracked. Keep the two eggs with golden rings whole. Wait until the cook bar is green, then serve before the crack spreads to them.",
    targetOffsets: [5, -6],
    minT: 4,
    threshold: 0.8,
    seconds: 14,
    choices: [GENTLE],
  },
  {
    id: 2,
    title: "Mind the spread",
    blurb: "The golden eggs are close to the crack this time and they need a longer cook. Pick the heat that spreads slowly enough.",
    targetOffsets: [3, 4],
    minT: 8,
    threshold: 0.7,
    seconds: 12,
    choices: [HOT, GENTLE],
  },
  {
    id: 3,
    title: "Put a lid on it",
    blurb: "The golden eggs sit right next to the crack and need a very long cook. No heat survives that. Find the pan where nothing can scramble.",
    targetOffsets: [-1, 1, 2],
    minT: 20,
    threshold: 0.9,
    seconds: 11,
    choices: [HOT, STIR, LID],
  },
  {
    id: 4,
    title: "Catch the echo",
    blurb: "No lid this time, and everything will scramble. Watch for the moment the golden eggs pull themselves back together, and serve then.",
    targetOffsets: [3, 4, 5],
    minT: 12,
    threshold: 0.82,
    seconds: 11,
    choices: [STIR],
  },
  {
    id: 5,
    title: "Hot pan, long cook",
    blurb: "Edge eggs, long cook, fast clock. One pan gives you plenty of time, one gives you a split second and one never works. Choose, then time it.",
    targetOffsets: [5, -6],
    minT: 15,
    threshold: 0.85,
    seconds: 8,
    choices: [GENTLE, HOT, STIR],
  },
];
