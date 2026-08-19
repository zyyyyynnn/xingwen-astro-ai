import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { asEntityId } from "@xingwen/domain";
import type { WwtSceneVisualizationReview } from "@xingwen/domain";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { WwtSceneControls } from "./wwt-scene-controls";

beforeAll(() => {
  // jsdom does not implement scrollIntoView, which Radix listboxes use.
  Element.prototype.scrollIntoView ??= () => undefined;
});

const viewportSpecs: WwtSceneVisualizationReview[] = [];

vi.mock("./wwt-viewport", () => ({
  WwtViewport: ({ spec }: { readonly spec: WwtSceneVisualizationReview }) => {
    viewportSpecs.push(spec);
    return <div data-testid="wwt-viewport" />;
  },
}));

afterEach(() => {
  cleanup();
  viewportSpecs.length = 0;
});

const publishedSpec: WwtSceneVisualizationReview = {
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
  fitsLayers: [
    {
      layerId: asEntityId("fits-layer-1"),
      sourceSnapshotId: asEntityId("snapshot-1"),
      contentRef: "fits.layer",
      contentHash: "sha256:" + "a".repeat(64),
      opacity: 0.8,
      stretch: "linear",
      colorMap: "gray",
      vmin: null,
      vmax: null,
    },
  ],
  tableLayers: [
    {
      layerId: asEntityId("table-layer-1"),
      sourceSnapshotId: asEntityId("snapshot-2"),
      contentRef: "table.layer",
      contentHash: "sha256:" + "b".repeat(64),
      mediaType: "text/csv",
      coordinates: {
        kind: "spherical",
        frame: "sky",
        longitudeField: "ra",
        latitudeField: "dec",
        longitudeUnit: "degrees",
        altitudeField: null,
      },
      timeSeries: null,
      sizeField: null,
      sizeScale: 1,
      colorToken: "brand",
      colorField: null,
      markerScale: "screen",
      opacity: 1,
    },
  ],
  annotations: [
    {
      annotationId: asEntityId("annotation-1"),
      kind: "circle",
      points: [{ raHours: 6.0, decDegrees: 24.0 }],
      label: "目标",
      colorToken: "warning",
      radiusDegrees: 0.05,
      lineWidth: 2,
      fill: false,
      fillColorToken: "warning",
    },
  ],
  tourSteps: [
    {
      stepId: asEntityId("step-1"),
      view: {
        kind: "coordinates",
        center: { raHours: 5.9, decDegrees: 24.2 },
        fieldOfViewDegrees: 2,
        rollDegrees: 0,
        transitionSeconds: 0,
      },
      observedAt: null,
      holdSeconds: 1,
    },
  ],
  tourAutoplay: false,
  tourLoop: false,
  readbacks: ["center_coordinates"],
  textAlternative: "昴星团天区场景。",
};

const loadContent = vi.fn(async () => new ArrayBuffer(0));

function lastViewportSpec(): WwtSceneVisualizationReview {
  const latest = viewportSpecs[viewportSpecs.length - 1];
  if (!latest) throw new Error("viewport was not rendered");
  return latest;
}

function renderControls() {
  return render(
    <WwtSceneControls
      spec={publishedSpec}
      versionNumber={1}
      loadContent={loadContent}
    />,
  );
}

describe("WwtSceneControls", () => {
  it("keeps every control on the fullscreen presentation state only", () => {
    renderControls();
    fireEvent.change(screen.getByLabelText("中心赤经（小时）"), {
      target: { value: "5.6" },
    });
    fireEvent.change(screen.getByLabelText("中心赤纬（度）"), {
      target: { value: "24.1" },
    });
    fireEvent.change(screen.getByLabelText("视场（度）"), {
      target: { value: "2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "前往坐标" }));

    const spec = lastViewportSpec();
    expect(spec.view.kind).toBe("coordinates");
    if (spec.view.kind !== "coordinates") return;
    expect(spec.view.center.raHours).toBe(5.6);
    expect(spec.view.center.decDegrees).toBe(24.1);
    expect(spec.view.fieldOfViewDegrees).toBe(2);
  });

  it("ignores invalid coordinate input without moving the scene", () => {
    renderControls();
    fireEvent.change(screen.getByLabelText("中心赤经（小时）"), {
      target: { value: "99" },
    });
    fireEvent.click(screen.getByRole("button", { name: "前往坐标" }));

    const spec = lastViewportSpec();
    expect(spec).toEqual(publishedSpec);
  });

  it("switches the background through the governed Select", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("combobox", { name: "背景天图" }));
    fireEvent.click(await screen.findByRole("option", { name: "Gaia DR3" }));

    await waitFor(() => expect(lastViewportSpec().background).toBe("gaia"));
  });

  it("toggles coordinate grids and constellation overlays", async () => {
    renderControls();
    fireEvent.pointerDown(screen.getByRole("button", { name: "坐标网格" }));
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: "银道网格" }),
    );
    await waitFor(() =>
      expect(lastViewportSpec().coordinateGrids).toEqual([
        { system: "equatorial", labels: true },
        { system: "galactic", labels: true },
      ]),
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "星座叠加" }));
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: "星座边界" }),
    );
    await waitFor(() =>
      expect(lastViewportSpec().constellations.boundaries).toBe(true),
    );
  });

  it("switches time mode into bounded playback", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("combobox", { name: "时间模式" }));
    fireEvent.click(await screen.findByRole("option", { name: "时间回放" }));

    await waitFor(() => {
      const time = lastViewportSpec().time;
      expect(time.mode).toBe("playback");
      expect(time.rate).toBe(10);
      expect(time.observedAt).not.toBeNull();
    });
  });

  it("restores the published scene exactly", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("combobox", { name: "背景天图" }));
    fireEvent.click(await screen.findByRole("option", { name: "Gaia DR3" }));
    await waitFor(() => expect(lastViewportSpec().background).toBe("gaia"));

    fireEvent.click(screen.getByRole("button", { name: "恢复发布场景" }));
    await waitFor(() => expect(lastViewportSpec()).toEqual(publishedSpec));
  });

  it("toggles layer visibility without touching the published spec", async () => {
    renderControls();
    fireEvent.pointerDown(screen.getByRole("button", { name: "图层" }));
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: "FITS 图层 1" }),
    );
    await waitFor(() =>
      expect(lastViewportSpec().fitsLayers[0]?.opacity).toBe(0),
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "图层" }));
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: "表格图层 1" }),
    );
    await waitFor(() =>
      expect(lastViewportSpec().tableLayers[0]?.opacity).toBe(0),
    );

    fireEvent.pointerDown(screen.getByRole("button", { name: "图层" }));
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: "FITS 图层 1" }),
    );
    await waitFor(() =>
      expect(lastViewportSpec().fitsLayers[0]?.opacity).toBe(0.8),
    );
  });

  it("shows and hides scene annotations on demand", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("button", { name: "隐藏标注" }));
    await waitFor(() => expect(lastViewportSpec().annotations).toEqual([]));

    fireEvent.click(screen.getByRole("button", { name: "显示标注" }));
    await waitFor(() =>
      expect(lastViewportSpec().annotations).toEqual(publishedSpec.annotations),
    );
  });

  it("plays and stops the bounded scene tour", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("button", { name: "播放巡览" }));
    await waitFor(() => expect(lastViewportSpec().tourAutoplay).toBe(true));

    fireEvent.click(screen.getByRole("button", { name: "停止巡览" }));
    await waitFor(() => expect(lastViewportSpec().tourAutoplay).toBe(false));
  });
});
