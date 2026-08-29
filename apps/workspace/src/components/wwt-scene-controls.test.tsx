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

import {
  transitionSceneBackground,
  transitionToTrackedObject,
  WwtSceneControls,
} from "./wwt-scene-controls";

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

const trackedObjectSpec: WwtSceneVisualizationReview = {
  ...publishedSpec,
  background: "solar_system",
  constellations: {
    boundaries: false,
    figures: false,
    pictures: false,
    labels: false,
  },
  view: {
    kind: "tracked_object",
    target: "jupiter",
    fieldOfViewDegrees: 2.5,
    rollDegrees: 15,
    transitionSeconds: 0,
  },
  time: {
    mode: "playback",
    observedAt: "2026-08-19T03:04:00.000Z",
    rate: 42,
  },
  observer: {
    latitudeDegrees: 26.6,
    longitudeDegrees: 106.7,
    elevationMeters: 1070,
    localHorizonMode: true,
  },
};

function lastViewportSpec(): WwtSceneVisualizationReview {
  const latest = viewportSpecs[viewportSpecs.length - 1];
  if (!latest) throw new Error("viewport was not rendered");
  return latest;
}

function renderControls() {
  return render(
    <WwtSceneControls spec={publishedSpec} loadContent={loadContent} />,
  );
}

function openPositionControls() {
  fireEvent.click(screen.getByRole("button", { name: "定位与视角" }));
}

function openTimeControls() {
  fireEvent.click(screen.getByRole("button", { name: "时间设置" }));
}

describe("WwtSceneControls", () => {
  it("normalizes track-object transitions into a backend-valid solar scene", () => {
    const tracked = transitionToTrackedObject(
      {
        ...publishedSpec,
        foreground: { imageSet: "wise", opacity: 0.4 },
        precessionChart: true,
      },
      "mars",
    );

    expect(tracked.view).toEqual({
      kind: "tracked_object",
      target: "mars",
      fieldOfViewDegrees: 1.5,
      rollDegrees: 0,
      transitionSeconds: 1,
    });
    expect(tracked.background).toBe("solar_system");
    expect(tracked.foreground).toBeNull();
    expect(Object.values(tracked.constellations)).toEqual([
      false,
      false,
      false,
      false,
    ]);
    expect(tracked.precessionChart).toBe(false);
  });

  it("clears incompatible overlays on solar background and does not restore them", () => {
    const solar = transitionSceneBackground(
      {
        ...publishedSpec,
        foreground: { imageSet: "wise", opacity: 0.4 },
        precessionChart: true,
      },
      "solar_system",
    );
    const sky = transitionSceneBackground(solar, "gaia");

    expect(solar.foreground).toBeNull();
    expect(Object.values(solar.constellations).every((value) => !value)).toBe(
      true,
    );
    expect(solar.precessionChart).toBe(false);
    expect(sky.background).toBe("gaia");
    expect(sky.foreground).toBeNull();
    expect(sky.constellations).toEqual(solar.constellations);
    expect(sky.precessionChart).toBe(false);
  });

  it("initializes control drafts from the published coordinates spec", () => {
    renderControls();
    openPositionControls();
    expect(screen.getByLabelText("中心赤经（小时）")).toHaveValue("6");
    expect(screen.getByLabelText("中心赤纬（度）")).toHaveValue("24");
    expect(screen.getByLabelText("视场（度）")).toHaveValue("1.5");
    expect(screen.getByLabelText("相机滚转（度）")).toHaveValue("0");
  });

  it("initializes drafts from a tracked-object spec with observer and time", () => {
    render(
      <WwtSceneControls spec={trackedObjectSpec} loadContent={loadContent} />,
    );
    openPositionControls();
    expect(screen.getByLabelText("中心赤经（小时）")).toHaveValue("");
    expect(screen.getByLabelText("中心赤纬（度）")).toHaveValue("");
    expect(screen.getByLabelText("视场（度）")).toHaveValue("2.5");
    expect(screen.getByLabelText("相机滚转（度）")).toHaveValue("15");
    openTimeControls();
    expect(screen.getByLabelText("时间倍率")).toHaveValue("42");
    expect(screen.getByLabelText("观测时间（UTC）")).toHaveValue(
      "2026-08-19T03:04",
    );
    expect(
      screen.getByRole("combobox", { name: "跟踪天体" }),
    ).toHaveTextContent("木星");
  });

  it("keeps every control on the fullscreen presentation state only", () => {
    renderControls();
    openPositionControls();
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
    openPositionControls();
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

  it("disables the AltAz grid until an observer is configured", async () => {
    renderControls();
    fireEvent.pointerDown(screen.getByRole("button", { name: "坐标网格" }));
    const altaz = await screen.findByRole("menuitemcheckbox", {
      name: "地平网格（需先设置观测点）",
    });
    expect(altaz).toHaveAttribute("data-disabled");
    fireEvent.click(altaz);
    expect(lastViewportSpec().coordinateGrids).toEqual(
      publishedSpec.coordinateGrids,
    );
  });

  it("prevents a tracked-object scene from selecting an invalid sky background", async () => {
    render(
      <WwtSceneControls spec={trackedObjectSpec} loadContent={loadContent} />,
    );
    fireEvent.click(screen.getByRole("combobox", { name: "背景天图" }));
    const gaia = await screen.findByRole("option", { name: "Gaia DR3" });
    expect(gaia).toHaveAttribute("data-disabled");
    fireEvent.click(gaia);
    expect(lastViewportSpec().background).toBe("solar_system");
  });

  it("switches time mode into bounded playback", async () => {
    renderControls();
    openTimeControls();
    fireEvent.click(screen.getByRole("combobox", { name: "时间模式" }));
    fireEvent.click(await screen.findByRole("option", { name: "时间回放" }));

    await waitFor(() => {
      const time = lastViewportSpec().time;
      expect(time.mode).toBe("playback");
      expect(time.rate).toBe(10);
      expect(time.observedAt).not.toBeNull();
    });
  });

  it("restores the published scene and control drafts exactly", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("combobox", { name: "背景天图" }));
    fireEvent.click(await screen.findByRole("option", { name: "Gaia DR3" }));
    await waitFor(() => expect(lastViewportSpec().background).toBe("gaia"));

    openPositionControls();
    fireEvent.change(screen.getByLabelText("中心赤经（小时）"), {
      target: { value: "5.6" },
    });
    fireEvent.change(screen.getByLabelText("视场（度）"), {
      target: { value: "3" },
    });
    fireEvent.click(screen.getByRole("button", { name: "前往坐标" }));

    fireEvent.click(screen.getByRole("button", { name: "恢复发布场景" }));
    await waitFor(() => expect(lastViewportSpec()).toEqual(publishedSpec));
    expect(screen.getByLabelText("中心赤经（小时）")).toHaveValue("6");
    expect(screen.getByLabelText("中心赤纬（度）")).toHaveValue("24");
    expect(screen.getByLabelText("视场（度）")).toHaveValue("1.5");
    expect(screen.getByLabelText("相机滚转（度）")).toHaveValue("0");
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

  it("applies an explicit camera roll and keeps it across navigation", async () => {
    renderControls();
    openPositionControls();
    fireEvent.change(screen.getByLabelText("中心赤经（小时）"), {
      target: { value: "5.6" },
    });
    fireEvent.change(screen.getByLabelText("中心赤纬（度）"), {
      target: { value: "24.1" },
    });
    fireEvent.change(screen.getByLabelText("相机滚转（度）"), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "前往坐标" }));
    await waitFor(() => expect(lastViewportSpec().view.rollDegrees).toBe(30));

    // Navigating again without touching the roll input must keep the current
    // scene roll instead of resetting it to zero.
    fireEvent.change(screen.getByLabelText("相机滚转（度）"), {
      target: { value: "" },
    });
    fireEvent.change(screen.getByLabelText("中心赤经（小时）"), {
      target: { value: "6.2" },
    });
    fireEvent.click(screen.getByRole("button", { name: "前往坐标" }));
    await waitFor(() => {
      const view = lastViewportSpec().view;
      expect(view.kind).toBe("coordinates");
      if (view.kind !== "coordinates") return;
      expect(view.center.raHours).toBe(6.2);
      expect(view.rollDegrees).toBe(30);
    });
  });

  it("rejects an out-of-range camera roll with a visible error", async () => {
    renderControls();
    openPositionControls();
    fireEvent.change(screen.getByLabelText("中心赤经（小时）"), {
      target: { value: "5.6" },
    });
    fireEvent.change(screen.getByLabelText("中心赤纬（度）"), {
      target: { value: "24.1" },
    });
    fireEvent.change(screen.getByLabelText("相机滚转（度）"), {
      target: { value: "400" },
    });
    fireEvent.click(screen.getByRole("button", { name: "前往坐标" }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(lastViewportSpec()).toEqual(publishedSpec);
  });

  it("tracks a solar-system object while preserving FOV and roll", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("combobox", { name: "跟踪天体" }));
    fireEvent.click(await screen.findByRole("option", { name: "木星" }));
    fireEvent.click(screen.getByRole("button", { name: "跟踪天体" }));

    await waitFor(() => {
      const view = lastViewportSpec().view;
      expect(view.kind).toBe("tracked_object");
      if (view.kind !== "tracked_object") return;
      expect(view.target).toBe("jupiter");
      expect(view.fieldOfViewDegrees).toBe(
        publishedSpec.view.fieldOfViewDegrees,
      );
      expect(view.rollDegrees).toBe(publishedSpec.view.rollDegrees);
    });
  });

  it("applies validated observer coordinates", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("button", { name: "观测点" }));
    fireEvent.change(await screen.findByLabelText("观测点纬度（度）"), {
      target: { value: "26.6" },
    });
    fireEvent.change(screen.getByLabelText("观测点经度（度）"), {
      target: { value: "106.7" },
    });
    fireEvent.change(screen.getByLabelText("观测点海拔（米）"), {
      target: { value: "1070" },
    });
    fireEvent.click(screen.getByRole("button", { name: "应用观测点" }));

    await waitFor(() =>
      expect(lastViewportSpec().observer).toEqual({
        latitudeDegrees: 26.6,
        longitudeDegrees: 106.7,
        elevationMeters: 1070,
        localHorizonMode: false,
      }),
    );
  });

  it("rejects an out-of-range observer latitude", async () => {
    renderControls();
    fireEvent.click(screen.getByRole("button", { name: "观测点" }));
    fireEvent.change(await screen.findByLabelText("观测点纬度（度）"), {
      target: { value: "95" },
    });
    fireEvent.click(screen.getByRole("button", { name: "应用观测点" }));

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(lastViewportSpec().observer).toBeNull();
  });

  it("fixes the observation time as explicit UTC", async () => {
    renderControls();
    openTimeControls();
    fireEvent.change(screen.getByLabelText("观测时间（UTC）"), {
      target: { value: "2026-08-19T03:04" },
    });
    fireEvent.click(screen.getByRole("button", { name: "固定观测时间" }));

    await waitFor(() => {
      const time = lastViewportSpec().time;
      expect(time.mode).toBe("paused");
      expect(time.observedAt).toBe("2026-08-19T03:04:00.000Z");
    });
  });
});
