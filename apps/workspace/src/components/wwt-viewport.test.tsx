import { asEntityId, type WwtSceneVisualizationReview } from "@xingwen/domain";
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const wwt = vi.hoisted(() => ({
  constructor: vi.fn(),
  backgrounds: vi.fn(),
  clearAnnotations: vi.fn(),
  goto: vi.fn(async (...args: unknown[]) => {
    void args;
  }),
  gotoTarget: vi.fn(async (...args: unknown[]) => {
    void args;
  }),
  setNow: vi.fn(),
  setTimeRate: vi.fn(),
  setSyncToClock: vi.fn(),
  syncTime: vi.fn(),
  setForegroundOpacity: vi.fn(),
  setForegroundImage: vi.fn(),
  setLocalHorizon: vi.fn(),
  setLocationLat: vi.fn(),
  setLocationLng: vi.fn(),
  setLocationAltitude: vi.fn(),
  setGalacticGrid: vi.fn((value: boolean) => value),
  setGalacticGridText: vi.fn((value: boolean) => value),
  setConstellationLabels: vi.fn(),
  setPrecessionChart: vi.fn(),
  setSolarScale: vi.fn(),
  addImageSetLayer: vi.fn(),
  setFitsLayerColormap: vi.fn(),
  stretchFitsLayer: vi.fn(),
  fitsLayer: {
    id: "wwt_fits_layer",
    set_opacity: vi.fn(),
    getFitsImage: vi.fn(() => ({
      fitsProperties: { lowerCut: 0, upperCut: 100 },
    })),
  },
  createSpreadsheetLayer: vi.fn(),
  tableLayer: {
    id: "wwt_table_layer",
    get_header: vi.fn(() => ["ra", "dec", "size", "class", "observed_at"]),
    set_coordinatesType: vi.fn(),
    set_lngColumn: vi.fn(),
    set_latColumn: vi.fn(),
    set_raUnits: vi.fn(),
    set_altColumn: vi.fn(),
    set_xAxisColumn: vi.fn(),
    set_yAxisColumn: vi.fn(),
    set_zAxisColumn: vi.fn(),
    set_cartesianScale: vi.fn(),
    set_cartesianCustomScale: vi.fn(),
    set_markerScale: vi.fn(),
    set_scaleFactor: vi.fn(),
    set_opacity: vi.fn(),
    set_color: vi.fn(),
    set_sizeColumn: vi.fn(),
    set_colorMapColumn: vi.fn(),
    set_timeSeries: vi.fn(),
    set_startDateColumn: vi.fn(),
    set_decay: vi.fn(),
  },
}));

wwt.createSpreadsheetLayer.mockReturnValue(wwt.tableLayer);
wwt.addImageSetLayer.mockResolvedValue(wwt.fitsLayer);

vi.mock("@wwtelescope/engine-helpers", () => ({
  WWTInstance: class {
    readonly si = {
      settings: {
        set_showGrid: vi.fn((value: boolean) => value),
        set_showEquatorialGridText: vi.fn((value: boolean) => value),
        set_showGalacticGrid: wwt.setGalacticGrid,
        set_showGalacticGridText: wwt.setGalacticGridText,
        set_showEclipticGrid: vi.fn((value: boolean) => value),
        set_showEclipticGridText: vi.fn((value: boolean) => value),
        set_showAltAzGrid: vi.fn((value: boolean) => value),
        set_showAltAzGridText: vi.fn((value: boolean) => value),
        set_localHorizonMode: wwt.setLocalHorizon,
        set_locationLat: wwt.setLocationLat,
        set_locationLng: wwt.setLocationLng,
        set_locationAltitude: wwt.setLocationAltitude,
        set_showConstellationBoundries: vi.fn(),
        set_showConstellationFigures: vi.fn(),
        set_showConstellationPictures: vi.fn(),
        set_showConstellationLabels: wwt.setConstellationLabels,
        set_showPrecessionChart: wwt.setPrecessionChart,
        set_solarSystemCosmos: vi.fn(),
        set_solarSystemLighting: vi.fn(),
        set_solarSystemMilkyWay: vi.fn(),
        set_solarSystemMinorPlanets: vi.fn(),
        set_solarSystemMinorOrbits: vi.fn(),
        set_solarSystemOrbits: vi.fn(),
        set_solarSystemPlanets: vi.fn(),
        set_solarSystemScale: wwt.setSolarScale,
        set_solarSystemStars: vi.fn(),
      },
      clearAnnotations: wwt.clearAnnotations,
      addAnnotation: vi.fn(),
      getRA: vi.fn(() => 10.25),
      getDec: vi.fn(() => -12.4),
    };
    readonly lm = {
      deleteLayerByID: vi.fn(),
      createSpreadsheetLayer: wwt.createSpreadsheetLayer,
    };
    readonly ctl = {
      renderContext: {
        get_fovAngle: vi.fn(() => 4),
        viewCamera: { rotation: 0 },
      },
    };

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

    setForegroundOpacity(value: number) {
      wwt.setForegroundOpacity(value);
    }

    setForegroundImageByName(name: string) {
      wwt.setForegroundImage(name);
    }

    setFitsLayerColormap(options: unknown) {
      wwt.setFitsLayerColormap(options);
    }

    stretchFitsLayer(options: unknown) {
      wwt.stretchFitsLayer(options);
    }

    gotoRADecZoom(...args: unknown[]) {
      return wwt.goto(...args);
    }

    gotoTarget(...args: unknown[]) {
      return wwt.gotoTarget(...args);
    }

    addImageSetLayer(options: unknown) {
      return wwt.addImageSetLayer(options);
    }
  },
}));

vi.mock("@wwtelescope/engine", () => ({
  Circle: class {},
  Color: { fromHex: vi.fn(() => ({})) },
  Place: class {
    readonly camera = { rotation: 0 };
    set_names() {}
    set_type() {}
    set_target() {}
    set_zoomLevel() {}
    get_camParams() {
      return this.camera;
    }
    set_camParams() {}
  },
  PolyLine: class {},
  SpaceTimeController: {
    get_now: vi.fn(() => new Date("2026-08-14T00:00:00Z")),
    set_now: wwt.setNow,
    set_timeRate: wwt.setTimeRate,
    set_syncToClock: wwt.setSyncToClock,
    syncTime: wwt.syncTime,
  },
}));

import { WwtViewport } from "./wwt-viewport";

afterEach(() => {
  cleanup();
  document.documentElement.style.removeProperty("--color-brand");
  vi.clearAllMocks();
});

const baseSpec: WwtSceneVisualizationReview = {
  mode: "wwt_scene",
  view: {
    kind: "coordinates",
    center: { raHours: 10.25, decDegrees: -12.4 },
    fieldOfViewDegrees: 4,
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
    figures: false,
    pictures: false,
    labels: false,
  },
  precessionChart: false,
  fitsLayers: [],
  tableLayers: [],
  annotations: [],
  tourSteps: [],
  tourAutoplay: false,
  tourLoop: false,
  readbacks: ["center_coordinates", "field_of_view", "current_time"],
  textAlternative: "DSS 中心视图。",
};

describe("WwtViewport", () => {
  it("keeps one official engine singleton across StrictMode and scene changes", async () => {
    document.documentElement.style.setProperty("--color-brand", "#336699");
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:wwt-local-content");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    let finishCapture: (() => void) | null = null;
    const toBlob = vi
      .spyOn(HTMLCanvasElement.prototype, "toBlob")
      .mockImplementation((callback) => {
        finishCapture = () =>
          callback(new Blob(["png"], { type: "image/png" }));
      });
    let downloadedName: string | null = null;
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(
      function captureDownloadName(this: HTMLAnchorElement) {
        downloadedName = this.download;
      },
    );
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(
      () =>
        ({
          fillStyle: "",
          fillRect: vi.fn(),
          getImageData: vi.fn(() => ({ data: [51, 102, 153, 255] })),
        }) as unknown as CanvasRenderingContext2D,
    );
    const loadContent = vi.fn(async () => new ArrayBuffer(0));
    const { container, rerender, unmount } = render(
      <StrictMode>
        <WwtViewport
          spec={baseSpec}
          versionNumber={2}
          loadContent={loadContent}
        />
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
    expect(
      screen.getByRole("region", { name: "WorldWide Telescope 交互场景" }),
    ).toHaveAttribute("tabindex", "0");
    expect(
      screen.getByLabelText("WorldWide Telescope 交互场景画布"),
    ).toHaveAttribute("tabindex", "0");
    fireEvent.click(screen.getByText("查看文本与表格替代视图"));
    expect(screen.getByText("当前场景没有 FITS 图层。")).toBeInTheDocument();
    expect(screen.getByText("当前场景没有表格图层。")).toBeInTheDocument();
    expect(screen.getByText("当前场景没有标注。")).toBeInTheDocument();
    expect(screen.getByText("DSS 中心视图。")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "下载场景 PNG" }));
    expect(screen.getByRole("button", { name: "正在生成 PNG" })).toBeDisabled();
    act(() => finishCapture?.());
    expect(await screen.findByRole("status")).toHaveTextContent("PNG 已下载");
    expect(downloadedName).toBe(["wwt-scene-v", 2, ".png"].join(""));

    toBlob.mockImplementationOnce(() => {
      throw new DOMException("Tainted canvas", "SecurityError");
    });
    fireEvent.click(screen.getByRole("button", { name: "下载场景 PNG" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "跨域污染或当前图形上下文不可导出",
    );

    rerender(
      <StrictMode>
        <WwtViewport
          spec={{ ...baseSpec, background: "wise" }}
          versionNumber={2}
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
          spec={{
            ...baseSpec,
            time: {
              mode: "paused",
              observedAt: "2026-08-14T00:00:00Z",
              rate: null,
            },
          }}
          versionNumber={2}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() => expect(wwt.setNow).toHaveBeenCalled());
    expect(wwt.setSyncToClock).toHaveBeenLastCalledWith(false);
    expect(wwt.setNow.mock.calls.at(-1)?.[0]).toEqual(
      new Date("2026-08-14T00:00:00Z"),
    );

    rerender(
      <StrictMode>
        <WwtViewport
          spec={{
            ...baseSpec,
            view: {
              kind: "tracked_object",
              target: "saturn",
              fieldOfViewDegrees: 8,
              rollDegrees: 12,
              transitionSeconds: 0,
            },
            time: {
              mode: "playback",
              observedAt: "2026-08-14T00:00:00Z",
              rate: 12,
            },
            observer: {
              latitudeDegrees: 31.2,
              longitudeDegrees: 121.5,
              elevationMeters: 5,
              localHorizonMode: true,
            },
            foreground: { imageSet: "wise", opacity: 0.4 },
            coordinateGrids: [{ system: "galactic", labels: true }],
            constellations: {
              ...baseSpec.constellations,
              labels: true,
            },
            precessionChart: true,
            solarSystem: {
              cosmos: true,
              lighting: true,
              milkyWay: true,
              minorPlanets: false,
              minorOrbits: false,
              orbits: true,
              planets: true,
              scale: 8,
              stars: true,
            },
          }}
          versionNumber={2}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() => expect(wwt.gotoTarget).toHaveBeenCalled());
    expect(wwt.setTimeRate).toHaveBeenLastCalledWith(12);
    expect(wwt.setLocalHorizon).toHaveBeenLastCalledWith(true);
    expect(wwt.setLocationLat).toHaveBeenLastCalledWith(31.2);
    expect(wwt.setGalacticGrid).toHaveBeenLastCalledWith(true);
    expect(wwt.setGalacticGridText).toHaveBeenLastCalledWith(true);
    expect(wwt.setForegroundImage).toHaveBeenLastCalledWith(
      "WISE All Sky (Infrared)",
    );
    expect(wwt.setForegroundOpacity).toHaveBeenLastCalledWith(40);
    expect(wwt.setConstellationLabels).toHaveBeenLastCalledWith(true);
    expect(wwt.setPrecessionChart).toHaveBeenLastCalledWith(true);
    expect(wwt.setSolarScale).toHaveBeenLastCalledWith(8);

    const fitsHash = "sha256:wwt-fits";
    loadContent.mockResolvedValueOnce(new Uint8Array([83, 73, 77, 80]).buffer);
    rerender(
      <StrictMode>
        <WwtViewport
          spec={{
            ...baseSpec,
            fitsLayers: [
              {
                layerId: asEntityId("layer_fits_cutout"),
                sourceSnapshotId: asEntityId("snapshot_fits_cutout"),
                contentRef: "must-not-be-loaded-as-fits-url",
                contentHash: fitsHash,
                opacity: 0.6,
                stretch: "sqrt",
                colorMap: "viridis",
                vmin: 4,
                vmax: 64,
              },
            ],
          }}
          versionNumber={2}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() => expect(loadContent).toHaveBeenCalledWith(fitsHash));
    expect(loadContent).not.toHaveBeenCalledWith(
      "must-not-be-loaded-as-fits-url",
    );
    await waitFor(() =>
      expect(wwt.fitsLayer.set_opacity).toHaveBeenLastCalledWith(0.6),
    );
    expect(wwt.addImageSetLayer).toHaveBeenLastCalledWith({
      url: "blob:wwt-local-content",
      mode: "fits",
      name: "layer_fits_cutout",
      goto: false,
    });
    expect(wwt.setFitsLayerColormap).toHaveBeenLastCalledWith({
      id: "wwt_fits_layer",
      name: "viridis",
    });
    expect(wwt.stretchFitsLayer).toHaveBeenLastCalledWith({
      id: "wwt_fits_layer",
      stretch: expect.anything(),
      vmin: 4,
      vmax: 64,
    });

    const tableHash = "sha256:wwt-table";
    loadContent.mockResolvedValueOnce(
      new TextEncoder().encode(
        "ra,dec,size,class,observed_at\n10.25,-12.4,3,A,2026-08-14",
      ).buffer,
    );
    rerender(
      <StrictMode>
        <WwtViewport
          spec={{
            ...baseSpec,
            tableLayers: [
              {
                layerId: asEntityId("layer_gaia_candidates"),
                sourceSnapshotId: asEntityId("snapshot_gaia_candidates"),
                contentRef: "must-not-be-loaded-as-url",
                contentHash: tableHash,
                mediaType: "text/csv",
                coordinates: {
                  kind: "spherical",
                  frame: "sky",
                  longitudeField: "ra",
                  latitudeField: "dec",
                  longitudeUnit: "degrees",
                  altitudeField: null,
                },
                timeSeries: {
                  timeField: "observed_at",
                  decayDays: 30,
                },
                sizeField: "size",
                sizeScale: 2,
                colorToken: "brand",
                colorField: "class",
                markerScale: "screen",
                opacity: 0.75,
              },
            ],
          }}
          versionNumber={2}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() => expect(loadContent).toHaveBeenCalledWith(tableHash));
    expect(loadContent).not.toHaveBeenCalledWith("must-not-be-loaded-as-url");
    expect(wwt.createSpreadsheetLayer).toHaveBeenLastCalledWith(
      "Sky",
      "layer_gaia_candidates",
      expect.stringContaining("ra,dec,size,class,observed_at"),
    );
    await waitFor(() =>
      expect(wwt.tableLayer.set_opacity).toHaveBeenLastCalledWith(0.75),
    );
    expect(wwt.tableLayer.set_lngColumn).toHaveBeenLastCalledWith(0);
    expect(wwt.tableLayer.set_latColumn).toHaveBeenLastCalledWith(1);
    expect(wwt.tableLayer.set_sizeColumn).toHaveBeenLastCalledWith(2);
    expect(wwt.tableLayer.set_colorMapColumn).toHaveBeenLastCalledWith(3);
    expect(wwt.tableLayer.set_startDateColumn).toHaveBeenLastCalledWith(4);

    rerender(
      <StrictMode>
        <WwtViewport
          spec={baseSpec}
          versionNumber={2}
          loadContent={loadContent}
        />
      </StrictMode>,
    );
    await waitFor(() =>
      expect(wwt.setLocalHorizon).toHaveBeenLastCalledWith(false),
    );
    expect(wwt.setGalacticGrid).toHaveBeenLastCalledWith(false);
    expect(wwt.setGalacticGridText).toHaveBeenLastCalledWith(false);
    expect(wwt.setConstellationLabels).toHaveBeenLastCalledWith(false);
    expect(wwt.setPrecessionChart).toHaveBeenLastCalledWith(false);
    expect(wwt.setSolarScale).toHaveBeenLastCalledWith(1);
    expect(wwt.setForegroundOpacity).toHaveBeenLastCalledWith(0);
    expect(wwt.setTimeRate).toHaveBeenLastCalledWith(1);

    unmount();
    await waitFor(() =>
      expect(
        document.querySelector("#xingwen-wwt-engine-root canvas"),
      ).toBeInTheDocument(),
    );
    expect(wwt.clearAnnotations).toHaveBeenCalled();
  });
});
