/** Paper Summary evidence must resolve through the shared Evidence store with bound-document page locators. */
import { expect, it } from "vitest";

import { createFixtureRepositories } from "../src/fixture-adapter";
import { exoplanetHostStarFixture } from "../src/fixture/exoplanet-host-star";

const repos = createFixtureRepositories(exoplanetHostStarFixture);

it("paper summary evidence carries real PDF page locators", async () => {
  const method = await repos.artifacts.getEvidence("evd_papsum_04" as never);
  expect(method).not.toBeNull();
  expect(method!.locator?.kind).toBe("paper_text");
  expect(
    method!.locator && "page" in method!.locator
      ? (method!.locator as { page: number | null }).page
      : null,
  ).toBe(4);
  expect(method!.quoteOrValue).toContain(
    "algorithmic procedures we adopted for calculating",
  );
});
