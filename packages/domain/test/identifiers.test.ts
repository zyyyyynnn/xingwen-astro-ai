import { describe, expect, it } from "vitest";

import { parseEntityId } from "../src/identifiers";

describe("parseEntityId", () => {
  it.each(["project-1", "a".repeat(128)])(
    "accepts an Identifier-compatible value: %s",
    (value) => {
      expect(parseEntityId(value)).toBe(value);
    },
  );

  it.each(["", " project-1", "project-1 ", "a".repeat(129)])(
    "rejects an invalid identifier boundary value",
    (value) => {
      expect(parseEntityId(value)).toBeNull();
    },
  );
});
