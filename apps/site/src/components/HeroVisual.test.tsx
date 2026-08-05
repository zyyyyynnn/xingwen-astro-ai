import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it } from "vitest";
import {
  createPoster,
  createResearchSceneModel,
  type ScenePalette,
} from "@xingwen/visual-engine";

import { HeroVisual } from "./HeroVisual";

const TEST_PALETTE: ScenePalette = {
  paper: "oklch(0.978 0.004 230)",
  ink: "oklch(0.38 0.022 235)",
  deep: "oklch(0.21 0.026 235)",
  soft: "oklch(0.885 0.011 235)",
  particle: "oklch(0.57 0.018 235)",
  anchor: "oklch(0.38 0.022 235)",
};

const poster = createPoster(createResearchSceneModel(42), TEST_PALETTE);

function mount(): { root: Root; container: HTMLElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  return { root, container };
}

afterEach(() => {
  document.body.innerHTML = "";
});

describe("HeroVisual", () => {
  it("renders the Poster <img> with the accessible label in initial HTML", async () => {
    const { root, container } = mount();
    await act(async () => {
      root.render(<HeroVisual poster={poster} seed={42} />);
    });
    const img = container.querySelector<HTMLImageElement>(".hero-poster");
    expect(img).not.toBeNull();
    expect(img?.getAttribute("alt")).toContain("系外行星 Transit");
    expect(img?.hasAttribute("hidden")).toBe(false);
    await act(async () => {
      root.unmount();
    });
  });

  it("keeps the Poster and never mounts a Canvas where WebGL2 is unavailable", async () => {
    const { root, container } = mount();
    await act(async () => {
      root.render(<HeroVisual poster={poster} seed={42} />);
    });
    expect(container.querySelector(".hero-poster")).not.toBeNull();
    expect(container.querySelector(".hero-canvas")).toBeNull();
    await act(async () => {
      root.unmount();
    });
  });

  it("cleans up its DOM subtree on unmount", async () => {
    const { root, container } = mount();
    await act(async () => {
      root.render(<HeroVisual poster={poster} seed={42} />);
    });
    await act(async () => {
      root.unmount();
    });
    expect(container.childNodes.length).toBe(0);
    expect(document.body.querySelector(".hero-visual")).toBeNull();
  });
});
