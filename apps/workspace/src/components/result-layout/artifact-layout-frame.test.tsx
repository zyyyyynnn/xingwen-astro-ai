import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ArtifactLayoutFrame } from "./artifact-layout-frame";

afterEach(cleanup);

describe("ArtifactLayoutFrame", () => {
  it("resets the active artifact scroll position when the result changes", () => {
    const { container, rerender } = render(
      <ArtifactLayoutFrame mode="data" scrollKey="version-1">
        <div>first result</div>
      </ArtifactLayoutFrame>,
    );
    const frame = container.querySelector<HTMLElement>(
      ".xw-artifact-layout-frame",
    );
    const scroller = container.querySelector<HTMLElement>(
      "[data-artifact-scroll-container]",
    );
    expect(frame).not.toBeNull();
    expect(scroller).not.toBeNull();
    if (!frame || !scroller) {
      throw new Error("Artifact layout scroll containers were not rendered");
    }

    frame.scrollTop = 140;
    frame.scrollLeft = 70;
    scroller.scrollTop = 280;
    scroller.scrollLeft = 90;

    rerender(
      <ArtifactLayoutFrame mode="data" scrollKey="version-2">
        <div>second result</div>
      </ArtifactLayoutFrame>,
    );

    expect(frame.scrollTop).toBe(0);
    expect(frame.scrollLeft).toBe(0);
    expect(scroller.scrollTop).toBe(0);
    expect(scroller.scrollLeft).toBe(0);
  });
});
