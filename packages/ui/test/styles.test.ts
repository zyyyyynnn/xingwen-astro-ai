import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const styles = readFileSync(resolve(process.cwd(), "src/styles.css"), "utf8");

describe("shared UI style invariants", () => {
  it("removes non-essential motion when reduced motion is requested", () => {
    const reducedMotion = styles.match(
      /@media \(prefers-reduced-motion: reduce\)\s*\{(?<body>[\s\S]+)\}\s*$/u,
    )?.groups?.body;

    expect(reducedMotion).toContain("transition: none");
    expect(reducedMotion).toContain("animation: none");
  });

  it("consumes semantic tokens without a Workspace or OpenHands bridge", () => {
    expect(styles).not.toMatch(/--(?:oh|raw|workspace)-/u);
    expect(styles).not.toMatch(/#[\da-f]{3,8}\b/iu);
  });
});
