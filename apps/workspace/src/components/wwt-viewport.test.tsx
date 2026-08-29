import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import type { WwtSceneVisualizationReview } from "@xingwen/domain";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WwtViewport } from "./wwt-viewport";

vi.mock("./wwt-session", () => ({
  openWwtSession: vi.fn(),
}));

const downloadBytes = vi.fn();
vi.mock("../presentation/browser-download", () => ({
  downloadBytes: (...args: unknown[]) => downloadBytes(...args),
}));

import { openWwtSession } from "./wwt-session";

const openSession = vi.mocked(openWwtSession);

afterEach(() => {
  cleanup();
  openSession.mockReset();
  downloadBytes.mockReset();
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
      <WwtViewport spec={sceneSpec} loadContent={loadContent} />,
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
      <WwtViewport spec={sceneSpec} loadContent={loadContent} />,
    );
    const second = render(
      <WwtViewport spec={sceneSpec} loadContent={loadContent} />,
    );
    expect(openSession).toHaveBeenCalledTimes(2);

    first.unmount();
    second.unmount();
    expect(close).toHaveBeenCalledTimes(2);
  });

  it("reuses the active lease when scene controls update the spec", async () => {
    const close = vi.fn();
    const renderScene = vi.fn(async () => null);
    openSession.mockReturnValue({ render: renderScene, close });

    const view = render(
      <WwtViewport spec={sceneSpec} loadContent={loadContent} />,
    );
    await screen.findByText(/交互场景已加载/);

    const nextSpec: WwtSceneVisualizationReview = {
      ...sceneSpec,
      coordinateGrids: [],
    };
    view.rerender(<WwtViewport spec={nextSpec} loadContent={loadContent} />);
    await waitFor(() => expect(renderScene).toHaveBeenCalledTimes(2));

    expect(openSession).toHaveBeenCalledTimes(1);
    expect(close).not.toHaveBeenCalled();
    view.unmount();
    expect(close).toHaveBeenCalledTimes(1);
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

    render(<WwtViewport spec={sceneSpec} loadContent={loadContent} />);
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
    render(<WwtViewport spec={sceneSpec} loadContent={loadContent} />);
    expect(screen.getByText("查看文本与表格替代视图")).toBeInTheDocument();
    expect(screen.getByText("昴星团天区场景。")).toBeInTheDocument();
    expect(screen.getByText(/RA 6.0000h · Dec 24.0000°/)).toBeInTheDocument();
    expect(screen.getByText("equatorial（含标签）")).toBeInTheDocument();
  });

  it("exports the scene canvas as a PNG download", async () => {
    openSession.mockReturnValue({
      render: vi.fn(async () => null),
      close: vi.fn(),
    });
    const toBlob = vi
      .spyOn(HTMLCanvasElement.prototype, "toBlob")
      .mockImplementation(function (this: HTMLCanvasElement, callback) {
        callback(new Blob(["scene"], { type: "image/png" }));
      });
    try {
      render(<WwtViewport spec={sceneSpec} loadContent={loadContent} />);
      await screen.findByText(/交互场景已加载/);
      const host = screen.getByRole("region", {
        name: "WorldWide Telescope 交互场景",
      });
      host.appendChild(document.createElement("canvas"));

      fireEvent.click(screen.getByRole("button", { name: "下载场景 PNG" }));
      await waitFor(() =>
        expect(downloadBytes).toHaveBeenCalledWith(
          expect.objectContaining({
            fileName: "wwt-scene.png",
            mediaType: "image/png",
          }),
        ),
      );
      expect(screen.getByText("PNG 已下载。")).toBeInTheDocument();
    } finally {
      toBlob.mockRestore();
    }
  });

  it("reports honestly when the canvas cannot be exported", async () => {
    openSession.mockReturnValue({
      render: vi.fn(async () => null),
      close: vi.fn(),
    });
    const toBlob = vi
      .spyOn(HTMLCanvasElement.prototype, "toBlob")
      .mockImplementation(function (this: HTMLCanvasElement, callback) {
        callback(null);
      });
    try {
      render(<WwtViewport spec={sceneSpec} loadContent={loadContent} />);
      await screen.findByText(/交互场景已加载/);
      const host = screen.getByRole("region", {
        name: "WorldWide Telescope 交互场景",
      });
      host.appendChild(document.createElement("canvas"));

      fireEvent.click(screen.getByRole("button", { name: "下载场景 PNG" }));
      expect(await screen.findByRole("alert")).toHaveTextContent(
        "浏览器未能从当前 WebGL 画布生成 PNG",
      );
    } finally {
      toBlob.mockRestore();
    }
  });
});
