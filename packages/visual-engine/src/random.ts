import type { DeterministicRandom } from "./types";

/**
 * mulberry32 — small fast deterministic PRNG.
 * Same seed always yields the same sequence.
 */
export function createDeterministicRandom(seed: number): DeterministicRandom {
  let state = seed >>> 0;

  function next(): number {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  }

  return {
    next,
    nextRange(min: number, max: number): number {
      return min + next() * (max - min);
    },
  };
}
