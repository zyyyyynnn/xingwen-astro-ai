import { afterEach, describe, expect, it } from "vitest";

import { readCssLengthInPixels } from "../upstream/openhands/src/components/features/conversation/conversation-tabs/conversation-tabs";

const root = document.documentElement;
const tokenNames = [
  "--test-length-px",
  "--test-length-rem",
  "--test-length-negative",
  "--test-length-unsupported",
];

afterEach(() => {
  tokenNames.forEach((name) => root.style.removeProperty(name));
  root.style.removeProperty("font-size");
});

describe("readCssLengthInPixels", () => {
  it("resolves the supported px and rem units", () => {
    root.style.setProperty("--test-length-px", "24px");
    root.style.setProperty("--test-length-rem", "1.5rem");
    root.style.fontSize = "16px";

    expect(readCssLengthInPixels("--test-length-px")).toBe(24);
    expect(readCssLengthInPixels("--test-length-rem")).toBe(24);
  });

  it("fails explicitly for missing or invalid required tokens", () => {
    expect(() => readCssLengthInPixels("--missing-length")).toThrow(
      "Workspace layout token --missing-length is missing.",
    );

    root.style.setProperty("--test-length-negative", "-1px");
    expect(() => readCssLengthInPixels("--test-length-negative")).toThrow(
      "Workspace layout token --test-length-negative is invalid.",
    );

    root.style.setProperty("--test-length-unsupported", "1em");
    expect(() => readCssLengthInPixels("--test-length-unsupported")).toThrow(
      "Workspace layout token --test-length-unsupported must resolve to px or rem.",
    );
  });

  it("fails explicitly when rem conversion lacks a valid root font size", () => {
    root.style.setProperty("--test-length-rem", "1rem");
    root.style.fontSize = "0px";

    expect(() => readCssLengthInPixels("--test-length-rem")).toThrow(
      "Workspace root font size is missing or invalid.",
    );
  });
});
