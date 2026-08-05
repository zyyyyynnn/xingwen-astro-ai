import { describe, expect, it } from "vitest";

import { createResearchSceneModel } from "../src/scene-model";
import { sampleSceneFrame } from "../src/sample-frame";
import type { FrameData } from "../src/types";

function filledRatio(frame: FrameData): number {
  return (
    frame.cells.filter((cell) => cell.alpha > 0.05).length / frame.cells.length
  );
}

function weightedColumnMean(frame: FrameData): number {
  let weight = 0;
  let sum = 0;
  for (let row = 0; row < frame.height; row++) {
    for (let col = 0; col < frame.width; col++) {
      const alpha = frame.cells[row * frame.width + col]?.alpha ?? 0;
      if (alpha > 0.05) {
        weight += alpha;
        sum += alpha * col;
      }
    }
  }
  return sum / weight;
}

function weightedRowMean(frame: FrameData): number {
  let weight = 0;
  let sum = 0;
  for (let row = 0; row < frame.height; row++) {
    for (let col = 0; col < frame.width; col++) {
      const alpha = frame.cells[row * frame.width + col]?.alpha ?? 0;
      if (alpha > 0.05) {
        weight += alpha;
        sum += alpha * row;
      }
    }
  }
  return sum / weight;
}

describe("sampleSceneFrame", () => {
  const model = createResearchSceneModel(42);

  it("is deterministic for the same time", () => {
    const a = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    const b = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    expect(a).toEqual(b);
  });

  it("covers a large part of the frame at full open (fold = 0)", () => {
    const frame = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    // 网格化低估密度:每粒子仅占一格,而 GPU 字符尺寸覆盖约半格。0.18 为实测下限。
    expect(filledRatio(frame)).toBeGreaterThan(0.18);
  });

  it("leaves the frame near-empty during the fold pause", () => {
    const frame = sampleSceneFrame(model, 1.8, { cols: 96, rows: 54 });
    // 近空场仍保留底部裁切线附近的弧瓣轮廓,故不为 0。
    expect(filledRatio(frame)).toBeLessThan(0.1);
  });

  it("weights the composition toward the right side", () => {
    const frame = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    expect(weightedColumnMean(frame)).toBeGreaterThan(frame.width * 0.52);
  });

  it("weights the composition toward the lower part", () => {
    const frame = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    expect(weightedRowMean(frame)).toBeGreaterThan(frame.height * 0.53);
  });

  it("reaches the bottom crop line", () => {
    const frame = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    const bottomRows = [frame.height - 3, frame.height - 2, frame.height - 1];
    const bottomFilled = bottomRows.some((row) =>
      [...frame.cells.slice(row * frame.width, (row + 1) * frame.width)].some(
        (cell) => cell.alpha > 0.05,
      ),
    );
    expect(bottomFilled).toBe(true);
  });

  it("keeps the anchor markers visible at full open", () => {
    const frame = sampleSceneFrame(model, 0.4, { cols: 96, rows: 54 });
    const anchors = frame.cells.filter((cell) => cell.char === "■");
    expect(anchors.length).toBeGreaterThan(0);
  });
});
