export type Quality = "high" | "medium" | "low";

export interface PosterSource {
  readonly svg: string;
  readonly dataUrl: string;
}

export interface PosterConfig {
  seed: number;
  width?: number;
  height?: number;
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

export interface RenderConfig {
  seed: number;
  width: number;
  height: number;
  quality: Quality;
  freezeTime?: number;
  canvas: HTMLCanvasElement;
}

export interface AsciiDitherRenderer {
  render(time: number): void;
  resize(width: number, height: number): void;
  dispose(): void;
  getFrameData(time: number): FrameData;
}

export interface VisualEngineConfig {
  seed: number;
  freezeTime?: number;
  quality: Quality;
  reducedMotion: boolean;
  canvas: HTMLCanvasElement;
  domAnchorLabel?: string;
}

export interface VisualEngine {
  start(): void;
  pause(): void;
  resume(): void;
  resize(width: number, height: number): void;
  dispose(): void;
  setQuality(quality: Quality): void;
  onContextLoss(handler: () => void): void;
  getDomAnchor(): HTMLElement | null;
  isRunning(): boolean;
  isDisposed(): boolean;
}
