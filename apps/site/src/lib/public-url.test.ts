import { describe, expect, test } from "vitest";

import { resolvePublicHttpUrl } from "./public-url";

const fallback = "http://localhost:5173/workspace";

describe("resolvePublicHttpUrl", () => {
  test("accepts public HTTP and HTTPS URLs", () => {
    expect(
      resolvePublicHttpUrl("https://example.test/workspace", fallback),
    ).toBe("https://example.test/workspace");
  });

  test.each([
    "javascript:alert(1)",
    "https://user:secret@example.test",
    "not a url",
  ])("falls back for unsafe public configuration: %s", (value) => {
    expect(resolvePublicHttpUrl(value, fallback)).toBe(fallback);
  });
});
