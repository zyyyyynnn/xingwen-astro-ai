import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { VISUAL_TOKEN_FALLBACK } from "../src/index";

const css = readFileSync(new URL("../src/base.css", import.meta.url), "utf8");

function rawValue(name: string): string {
  const match = new RegExp(`--${name}:\\s*var\\((--[a-z0-9-]+)\\)`, "u").exec(
    css,
  );
  if (!match) throw new Error(`missing semantic token --${name}`);
  const raw = new RegExp(`${match[1]}:\\s*([^;]+);`, "u").exec(css);
  if (!raw) throw new Error(`missing raw token ${match[1]}`);
  return raw[1].trim();
}

describe("VISUAL_TOKEN_FALLBACK", () => {
  it("mirrors the semantic visual tokens declared in base.css", () => {
    expect(VISUAL_TOKEN_FALLBACK.canvas).toBe(rawValue("color-canvas"));
    expect(VISUAL_TOKEN_FALLBACK.celestialInk).toBe(
      rawValue("color-visual-celestial-ink"),
    );
    expect(VISUAL_TOKEN_FALLBACK.celestialDeep).toBe(
      rawValue("color-visual-celestial-deep"),
    );
    expect(VISUAL_TOKEN_FALLBACK.celestialSoft).toBe(
      rawValue("color-visual-celestial-soft"),
    );
    expect(VISUAL_TOKEN_FALLBACK.particle).toBe(
      rawValue("color-visual-particle"),
    );
  });
});
