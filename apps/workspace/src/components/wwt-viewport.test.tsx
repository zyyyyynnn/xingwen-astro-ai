import type { WwtSceneVisualizationReview } from "@xingwen/domain";
import { cleanup, render, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const wwt = vi.hoisted(() => ({
  constructor: vi.fn(),
  backgrounds: vi.fn(),
  clearAnnotations: vi.fn(),
  goto: vi.fn(async (...args: unknown[]) => {
    void args;
  }),
  setNow: vi.fn(),
  setSyncToClock: vi.fn(),
  syncTime: vi.fn(),
}));

vi.mock("@wwtelescope/engine-helpers", () => ({
  WWTInstance: class {
    readonly si = {
      settings: {
        set_showGrid: vi.fn((value: boolean) => value),
        set_showGalacticGrid: vi.fn((value: boolean) => value),
        set_showEclipticGrid: vi.fn((value: boolean) => value),
        set_showAltAzGrid: vi.fn((value: boolean) => value),
      },
      clearAnnotations: wwt.clearAnnotations,
      addAnnotation: vi.fn(),
    };
    readonly lm = { deleteLayerByID: vi.fn() };

    constructor(options: { elId: string }) {
      wwt.constructor(options);
      document
        .getElementById(options.elId)
        ?.append(document.createElement("canvas"));
    }

    waitForReady() {
      return Promise.resolve();
    }

    setBackgroundImageByName(name: string) {
      wwt.backgrounds(name);
    }

    gotoRADecZoom(...args: unknown[]) {
      return wwt.goto(...args);
    }

    addImageSetLayer() {
      return Promise.reject(new Error("unexpected FITS layer"));
    }
  },
}));

vi.mock("@wwtelescope/engine", () => ({
  Circle: class {},
  PolyLine: class {},
  SpaceTimeController: {
    set_now: wwt.setNow,
    set_syncToClock: wwt.setSyncToClock,
    syncTime: wwt.syncTime,
  },
}));

import { WwtViewport } from "./wwt-viewport";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const baseSpec: WwtSceneVisualizationReview = {
  mode: "wwt_scene",
  center: { raHours: 10.25, decDegrees: -12.4 },
  fieldOfViewDegrees: 4,
  observedAt: null,
  background: "digitized_sky_survey",
  coordinateGrid: "equatorial",
  fitsLayers: [],
  annotations: [],
};

describe("WwtViewport", () => {
  it("keeps one official engine singleton across StrictMode and scene changes", async () => {
    const loadContent = vi.fn(async () => new ArrayBuffer(0));
    const { container, rerender, unmount } = render(
      <StrictMode>
        <WwtViewport spec={baseSpec} loadContent={loadContent} />
      </StrictMode>,
    );

    await waitFor(() =>
      expect(
        container.querySelector(".wwt-viewport__canvas canvas"),
      ).toBeInTheDocument(),
    );
    expect(wwt.constructor).toHaveBeenCalledTimes(1);
    expect(wwt.backgrounds).toHaveBeenLastCalledWith(
      "Digitized Sky Survey (Color)",
    );
    expect(wwt.syncTime).toHaveBeenCalled();

    rerender(
      <StrictMode>
        <WwtViewport
          spec={{ ...baseSpec, background: "wise" }}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() =>
      expect(wwt.backgrounds).toHaveBeenLastCalledWith(
        "WISE All Sky (Infrared)",
      ),
    );
    expect(wwt.constructor).toHaveBeenCalledTimes(1);

    rerender(
      <StrictMode>
        <WwtViewport
          spec={{ ...baseSpec, observedAt: "2026-08-14T00:00:00Z" }}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() => expect(wwt.setNow).toHaveBeenCalled());
    expect(wwt.setSyncToClock).toHaveBeenLastCalledWith(false);
    expect(wwt.setNow.mock.calls.at(-1)?.[0]).toEqual(
      new Date("2026-08-14T00:00:00Z"),
    );

    unmount();
    await waitFor(() =>
      expect(
        document.querySelector("#xingwen-wwt-engine-root canvas"),
      ).toBeInTheDocument(),
    );
    expect(wwt.clearAnnotations).toHaveBeenCalled();
  });
});
