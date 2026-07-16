import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const css = readFileSync(new URL("./base.css", import.meta.url), "utf8");
const normalizedCss = css
  .replace(/\s+/gu, " ")
  .replace(/\(\s+/gu, "(")
  .replace(/\s+\)/gu, ")");

describe("base color tokens", () => {
  it("exposes the current cold-paper semantic color contract", () => {
    const expected = [
      "--color-canvas: var(--raw-paper-50)",
      "--color-surface: color-mix(in oklch, var(--raw-paper-0) 86%, var(--raw-haze-50))",
      "--color-ink-primary: var(--raw-gray-900)",
      "--color-ink-secondary: var(--raw-gray-600)",
      "--color-border: var(--raw-gray-200)",
      "--color-brand: var(--raw-haze-600)",
      "--color-focus: var(--raw-haze-500)",
    ];

    for (const declaration of expected) {
      expect(normalizedCss).toContain(declaration);
    }

    expect(css).not.toMatch(/#[0-9a-f]{3,8}\b/i);
  });
});
