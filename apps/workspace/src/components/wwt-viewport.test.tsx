import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { WwtSceneVisualizationReview } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WwtViewport } from "./wwt-viewport";

vi.mock("./wwt-session", () => ({
  openWwtSession: vi.fn(),
}));

import { openWwtSession } from "./wwt-session";

const openSession = vi.mocked(openWwtSession);

afterEach(() => {
  cleanup();
  openSession.mockReset();
});

const sceneSpec: WwtSceneVisualizationReview = {
  mode: "wwt_scene",
  view: {
    kind: "coordinates",
    center: { raHours: 6.0, decDegrees: 24.0 },
    fieldOfViewDegrees: 1.5,
    rollDegrees: 0,
    transitionSeconds: 0,
  },
  time: { mode: "system_clock", observedAt: null, rate: null },
  observer: null,
  background: "digitized_sky_survey",
  foreground: null,
  solarSystem: null,
  coordinateGrids: [{ system: "equatorial", labels: true }],
  constellations: {
    boundaries: false,
    figures: true,
    pictures: false,
    labels: true,
  },
  precessionChart: false,
  fitsLayers: [],
  tableLayers: [],
  annotations: [],
  tourSteps: [],
  tourAutoplay: false,
  tourLoop: false,
  readbacks: ["center_coordinates", "field_of_view"],
  textAlternative: "昴星团天区场景。",
};

const loadContent = vi.fn(async () => new ArrayBuffer(0));

describe("WwtViewport", () => {
  it("opens a session lease on mount and closes it on unmount", async () => {
    const close = vi.fn();
    const renderScene = vi.fn(async () => ({
      centerCoordinates: { raHours: 5.6, decDegrees: 24.1 },
      fieldOfViewDegrees: 1.4,
      cameraRollDegrees: null,
      currentTime: null,
    }));
    openSession.mockReturnValue({ render: renderScene, close });

    const { unmount } = render(
      <WwtViewport
        spec={sceneSpec}
        versionNumber={1}
        loadContent={loadContent}
      />,
    );
    expect(openSession).toHaveBeenCalledTimes(1);
    await screen.findByText(/实际中心/);
    expect(renderScene).toHaveBeenCalledWith(
      sceneSpec,
      expect.objectContaining({ loadContent: expect.any(Function) }),
    );
    expect(screen.getByText(/RA 5.6000h/)).toBeInTheDocument();

    unmount();
    expect(close).toHaveBeenCalledTimes(1);
  });

  it("closes every lease when viewports unmount in turn", async () => {
    const close = vi.fn();
    const renderScene = vi.fn(async () => null);
    openSession.mockReturnValue({ render: renderScene, close });

    const first = render(
      <WwtViewport
        spec={sceneSpec}
        versionNumber={1}
        loadContent={loadContent}
      />,
    );
    const second = render(
      <WwtViewport
        spec={sceneSpec}
        versionNumber={1}
        loadContent={loadContent}
      />,
    );
    expect(openSession).toHaveBeenCalledTimes(2);

    first.unmount();
    second.unmount();
    expect(close).toHaveBeenCalledTimes(2);
  });

  it("offers retry after a scene initialization failure", async () => {
    let attempt = 0;
    openSession.mockImplementation(() => ({
      render: () => {
        attempt += 1;
        return attempt === 1
          ? Promise.reject(new Error("WorldWide Telescope 初始化失败"))
          : Promise.resolve(null);
      },
      close: vi.fn(),
    }));

    render(
      <WwtViewport
        spec={sceneSpec}
        versionNumber={1}
        loadContent={loadContent}
      />,
    );
    expect(
      await screen.findByText("WorldWide Telescope 初始化失败"),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重新加载交互视图" }));
    await screen.findByText(/交互场景已加载/);
    expect(attempt).toBe(2);
  });

  it("keeps the text and table fallback readable without the engine", () => {
    openSession.mockReturnValue({
      render: () => new Promise(() => undefined),
      close: vi.fn(),
    });
    render(
      <WwtViewport
        spec={sceneSpec}
        versionNumber={1}
        loadContent={loadContent}
      />,
    );
    expect(screen.getByText("查看文本与表格替代视图")).toBeInTheDocument();
    expect(screen.getByText("昴星团天区场景。")).toBeInTheDocument();
    expect(screen.getByText(/RA 6.0000h · Dec 24.0000°/)).toBeInTheDocument();
    expect(screen.getByText("equatorial（含标签）")).toBeInTheDocument();
  });
});
