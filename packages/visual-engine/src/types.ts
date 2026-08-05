export type Quality = "high" | "medium" | "low";

export interface PosterSource {
  readonly svg: string;
  readonly dataUrl: string;
}

export interface DeterministicRandom {
  next(): number;
  nextRange(min: number, max: number): number;
}

export interface FrameCell {
  readonly char: string;
  readonly alpha: number;
}

export interface FrameData {
  readonly width: number;
  readonly height: number;
  readonly cells: readonly FrameCell[];
}
