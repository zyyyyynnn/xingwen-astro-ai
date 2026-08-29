import type {
  ContentHash,
  FitsImageVisualizationReview,
  WwtAnnotationReview,
  WwtCoordinateGridReview,
  WwtSceneVisualizationReview,
  WwtTableLayerReview,
  WwtViewReview,
} from "@xingwen/domain";
import {
  AltUnits,
  CoordinatesType,
  ImageSetType,
  MarkerScales,
  RAUnits,
  ScaleTypes,
  SolarSystemObjects,
} from "@wwtelescope/engine-types";

export type WwtSpec =
  FitsImageVisualizationReview | WwtSceneVisualizationReview;

export interface WwtSceneOptions {
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly onProgress: (message: string) => void;
  readonly onAsyncError?: (error: unknown) => void;
}

export interface WwtSceneReadback {
  readonly centerCoordinates: {
    readonly raHours: number;
    readonly decDegrees: number;
  } | null;
  readonly fieldOfViewDegrees: number | null;
  readonly cameraRollDegrees: number | null;
  readonly currentTime: string | null;
}

interface EngineSession {
  readonly canvas: HTMLCanvasElement;
  readonly engine: typeof import("@wwtelescope/engine");
  readonly instance: import("@wwtelescope/engine-helpers").WWTInstance;
  readonly layers: Set<import("@wwtelescope/engine").Layer>;
  readonly objectUrls: Set<string>;
}

export interface WwtSessionLease {
  readonly render: (
    spec: WwtSpec,
    options: WwtSceneOptions,
  ) => Promise<WwtSceneReadback | null>;
  readonly close: () => void;
}

const ENGINE_ROOT_ID = "xingwen-wwt-engine-root";

let engineRoot: HTMLDivElement | null = null;
let engineSessionPromise: Promise<EngineSession> | null = null;
let activeLease: symbol | null = null;
let renderQueue: Promise<void> = Promise.resolve();

class SupersededWwtLeaseError extends Error {
  constructor() {
    super("WWT scene lease was superseded");
    this.name = "SupersededWwtLeaseError";
  }
}

function parkingRoot(host: HTMLElement): HTMLDivElement {
  if (engineRoot) return engineRoot;
  const root = document.createElement("div");
  root.id = ENGINE_ROOT_ID;
  root.setAttribute("aria-hidden", "true");
  root.style.position = "fixed";
  root.style.insetInlineStart = "-10000px";
  root.style.insetBlockStart = "-10000px";
  root.style.inlineSize = `${Math.max(host.clientWidth, 1)}px`;
  root.style.blockSize = `${Math.max(host.clientHeight, 1)}px`;
  root.style.overflow = "hidden";
  root.style.pointerEvents = "none";
  document.body.append(root);
  engineRoot = root;
  return root;
}

function tokenColor(token: WwtAnnotationReview["colorToken"]): string {
  const variable = {
    brand: "--color-brand",
    information: "--color-info",
    success: "--color-success",
    warning: "--color-warning",
    error: "--color-error",
    neutral: "--color-ink-secondary",
  }[token];
  const source = getComputedStyle(document.documentElement)
    .getPropertyValue(variable)
    .trim();
  if (!source) throw new Error(`主题缺少 WWT 标注颜色 Token：${variable}`);
  const canvas = document.createElement("canvas");
  canvas.width = 1;
  canvas.height = 1;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) throw new Error("浏览器无法解析 WWT 标注颜色 Token");
  context.fillStyle = source;
  context.fillRect(0, 0, 1, 1);
  const [red = 255, green = 255, blue = 255] = context.getImageData(
    0,
    0,
    1,
    1,
  ).data;
  return `${String.fromCodePoint(35)}${[red, green, blue]
    .map((value) => value.toString(16).padStart(2, "0"))
    .join("")}`;
}

function configureGrid(
  settings: import("@wwtelescope/engine").Settings,
  grids: readonly WwtCoordinateGridReview[],
) {
  const config = new Map(grids.map((grid) => [grid.system, grid.labels]));
  settings.set_showGrid(config.has("equatorial"));
  settings.set_showEquatorialGridText(config.get("equatorial") ?? false);
  settings.set_showGalacticGrid(config.has("galactic"));
  settings.set_showGalacticGridText(config.get("galactic") ?? false);
  settings.set_showEclipticGrid(config.has("ecliptic"));
  settings.set_showEclipticGridText(config.get("ecliptic") ?? false);
  settings.set_showAltAzGrid(config.has("altaz"));
  settings.set_showAltAzGridText(config.get("altaz") ?? false);
}

function configureAnnotation(
  annotation: WwtAnnotationReview,
  session: EngineSession,
  fieldOfViewDegrees: number,
) {
  const color = tokenColor(annotation.colorToken);
  if (annotation.kind === "line") {
    const line = new session.engine.PolyLine();
    annotation.points.forEach((point) =>
      line.addPoint(point.raHours * 15, point.decDegrees),
    );
    line.set_lineColor(color);
    line.set_lineWidth(annotation.lineWidth);
    line.set_label(annotation.label ?? "");
    line.set_showHoverLabel(annotation.label !== null);
    session.instance.si.addAnnotation(line);
    return;
  }
  const point = annotation.points[0];
  if (!point) return;
  const circle = new session.engine.Circle();
  circle.setCenter(point.raHours * 15, point.decDegrees);
  circle.set_radius(
    annotation.radiusDegrees ?? Math.max(fieldOfViewDegrees * 0.008, 0.002),
  );
  circle.set_lineColor(color);
  circle.set_lineWidth(annotation.lineWidth);
  circle.set_fill(annotation.fill || annotation.kind === "label");
  circle.set_fillColor(tokenColor(annotation.fillColorToken));
  circle.set_opacity(annotation.kind === "label" ? 0.8 : 1);
  circle.set_label(annotation.label ?? "");
  circle.set_showHoverLabel(annotation.label !== null);
  session.instance.si.addAnnotation(circle);
}

function stretchType(
  stretch: FitsImageVisualizationReview["stretch"],
): ScaleTypes {
  return {
    linear: ScaleTypes.linear,
    sqrt: ScaleTypes.squareRoot,
    log: ScaleTypes.log,
    power: ScaleTypes.power,
    histogram_equalization: ScaleTypes.histogramEqualization,
  }[stretch];
}

function configureFitsLayer(
  session: EngineSession,
  layer: import("@wwtelescope/engine").ImageSetLayer,
  options: {
    readonly opacity: number;
    readonly stretch?: FitsImageVisualizationReview["stretch"];
    readonly colorMap?: FitsImageVisualizationReview["colorMap"];
    readonly vmin?: number | null;
    readonly vmax?: number | null;
  },
) {
  layer.set_opacity(options.opacity);
  const id = layer.id.toString();
  if (options.colorMap) {
    session.instance.setFitsLayerColormap({ id, name: options.colorMap });
  }
  const properties = layer.getFitsImage()?.fitsProperties;
  if (options.stretch && properties) {
    session.instance.stretchFitsLayer({
      id,
      stretch: stretchType(options.stretch),
      vmin: options.vmin ?? properties.lowerCut,
      vmax: options.vmax ?? properties.upperCut,
    });
  }
}

function assertLease(token: symbol) {
  if (activeLease !== token) throw new SupersededWwtLeaseError();
}

function resetScene(session: EngineSession) {
  session.instance.si.clearAnnotations();
  const settings = session.instance.si.settings;
  configureGrid(settings, []);
  settings.set_localHorizonMode(false);
  settings.set_locationLat(0);
  settings.set_locationLng(0);
  settings.set_locationAltitude(0);
  settings.set_showConstellationBoundries(false);
  settings.set_showConstellationFigures(false);
  settings.set_showConstellationPictures(false);
  settings.set_showConstellationLabels(false);
  settings.set_showPrecessionChart(false);
  settings.set_solarSystemCosmos(false);
  settings.set_solarSystemLighting(true);
  settings.set_solarSystemMilkyWay(true);
  settings.set_solarSystemMinorPlanets(false);
  settings.set_solarSystemMinorOrbits(false);
  settings.set_solarSystemOrbits(true);
  settings.set_solarSystemPlanets(true);
  settings.set_solarSystemScale(1);
  settings.set_solarSystemStars(true);
  session.instance.setForegroundOpacity(0);
  session.engine.SpaceTimeController.set_timeRate(1);
  session.engine.SpaceTimeController.syncTime();
  session.layers.forEach((layer) =>
    session.instance.lm.deleteLayerByID(layer.id, true, true),
  );
  session.layers.clear();
  session.objectUrls.forEach((url) => URL.revokeObjectURL(url));
  session.objectUrls.clear();
}

function queue<T>(operation: () => Promise<T>): Promise<T> {
  const result = renderQueue.then(operation, operation);
  renderQueue = result.then(
    () => undefined,
    () => undefined,
  );
  return result;
}

function getEngineSession(host: HTMLElement): Promise<EngineSession> {
  if (engineSessionPromise) return engineSessionPromise;
  const root = parkingRoot(host);
  engineSessionPromise = Promise.all([
    import("@wwtelescope/engine-helpers"),
    import("@wwtelescope/engine"),
  ]).then(async ([{ WWTInstance }, engine]) => {
    const instance = new WWTInstance({
      elId: root.id,
      startInternalRenderLoop: true,
    });
    const canvas = root.querySelector("canvas");
    if (!(canvas instanceof HTMLCanvasElement)) {
      throw new Error("WorldWide Telescope 未创建 WebGL Canvas");
    }
    await instance.waitForReady();
    return {
      canvas,
      engine,
      instance,
      layers: new Set(),
      objectUrls: new Set(),
    };
  });
  return engineSessionPromise;
}

async function addFitsLayer(
  session: EngineSession,
  token: symbol,
  data: ArrayBuffer,
  options: {
    readonly name: string;
    readonly goto: boolean;
    readonly opacity: number;
    readonly stretch?: FitsImageVisualizationReview["stretch"];
    readonly colorMap?: FitsImageVisualizationReview["colorMap"];
    readonly vmin?: number | null;
    readonly vmax?: number | null;
  },
) {
  assertLease(token);
  const url = URL.createObjectURL(new Blob([data]));
  session.objectUrls.add(url);
  const layer = await session.instance.addImageSetLayer({
    url,
    mode: "fits",
    name: options.name,
    goto: options.goto,
  });
  session.layers.add(layer);
  assertLease(token);
  configureFitsLayer(session, layer, options);
}

const IMAGE_SET_NAMES = {
  digitized_sky_survey: "Digitized Sky Survey (Color)",
  gaia: "Gaia DR3",
  wise: "WISE All Sky (Infrared)",
  solar_system: "Solar System",
} as const;

function configureTime(
  session: EngineSession,
  time: WwtSceneVisualizationReview["time"],
) {
  const clock = session.engine.SpaceTimeController;
  if (time.mode === "system_clock") {
    clock.set_timeRate(1);
    clock.syncTime();
    return;
  }
  if (time.observedAt === null) {
    throw new Error(`WWT ${time.mode} 时间缺少 observedAt`);
  }
  clock.set_now(new Date(time.observedAt));
  if (time.mode === "paused") {
    clock.set_timeRate(1);
    clock.set_syncToClock(false);
    return;
  }
  if (time.rate === null || time.rate === 0) {
    throw new Error("WWT playback 时间缺少非零 rate");
  }
  clock.set_timeRate(time.rate);
  clock.set_syncToClock(true);
}

function configureObserver(
  settings: import("@wwtelescope/engine").Settings,
  observer: WwtSceneVisualizationReview["observer"],
) {
  if (observer === null || observer === undefined) {
    settings.set_locationLat(0);
    settings.set_locationLng(0);
    settings.set_locationAltitude(0);
    settings.set_localHorizonMode(false);
    return;
  }
  settings.set_locationLat(observer.latitudeDegrees);
  settings.set_locationLng(observer.longitudeDegrees);
  settings.set_locationAltitude(observer.elevationMeters);
  settings.set_localHorizonMode(observer.localHorizonMode);
}

function configureSceneAppearance(
  session: EngineSession,
  spec: WwtSceneVisualizationReview,
) {
  configureTime(session, spec.time);
  configureObserver(session.instance.si.settings, spec.observer);
  configureGrid(session.instance.si.settings, spec.coordinateGrids);
  configureOverlays(session.instance.si.settings, spec);
  session.instance.setBackgroundImageByName(IMAGE_SET_NAMES[spec.background]);
  if (spec.foreground === null) {
    session.instance.setForegroundOpacity(0);
  } else {
    session.instance.setForegroundImageByName(
      IMAGE_SET_NAMES[spec.foreground.imageSet],
    );
    session.instance.setForegroundOpacity(spec.foreground.opacity * 100);
  }
}

function canUpdateSceneInPlace(
  previous: WwtSpec | null,
  next: WwtSceneVisualizationReview,
): previous is WwtSceneVisualizationReview {
  return (
    previous?.mode === "wwt_scene" &&
    !previous.tourAutoplay &&
    !next.tourAutoplay &&
    previous.fitsLayers.length === next.fitsLayers.length &&
    previous.fitsLayers.every(
      (layer, index) => layer === next.fitsLayers[index],
    ) &&
    previous.tableLayers.length === next.tableLayers.length &&
    previous.tableLayers.every(
      (layer, index) => layer === next.tableLayers[index],
    )
  );
}

function configureOverlays(
  settings: import("@wwtelescope/engine").Settings,
  spec: WwtSceneVisualizationReview,
) {
  settings.set_showConstellationBoundries(spec.constellations.boundaries);
  settings.set_showConstellationFigures(spec.constellations.figures);
  settings.set_showConstellationPictures(spec.constellations.pictures);
  settings.set_showConstellationLabels(spec.constellations.labels);
  settings.set_showPrecessionChart(spec.precessionChart);
  const solar = spec.solarSystem;
  if (solar === null) return;
  settings.set_solarSystemCosmos(solar.cosmos);
  settings.set_solarSystemLighting(solar.lighting);
  settings.set_solarSystemMilkyWay(solar.milkyWay);
  settings.set_solarSystemMinorPlanets(solar.minorPlanets);
  settings.set_solarSystemMinorOrbits(solar.minorOrbits);
  settings.set_solarSystemOrbits(solar.orbits);
  settings.set_solarSystemPlanets(solar.planets);
  settings.set_solarSystemScale(solar.scale);
  settings.set_solarSystemStars(solar.stars);
}

async function gotoView(
  session: EngineSession,
  token: symbol,
  view: WwtViewReview,
) {
  assertLease(token);
  if (view.kind === "coordinates") {
    await session.instance.gotoRADecZoom(
      (view.center.raHours * Math.PI) / 12,
      (view.center.decDegrees * Math.PI) / 180,
      view.fieldOfViewDegrees,
      view.transitionSeconds === 0,
      (view.rollDegrees * Math.PI) / 180,
      view.transitionSeconds || undefined,
    );
    assertLease(token);
    return;
  }
  const place = new session.engine.Place();
  place.set_names([view.target]);
  place.set_type(ImageSetType.solarSystem);
  place.set_target(SolarSystemObjects[view.target]);
  place.set_zoomLevel(view.fieldOfViewDegrees);
  const camera = place.get_camParams();
  camera.rotation = view.rollDegrees;
  place.set_camParams(camera);
  await session.instance.gotoTarget({
    place,
    noZoom: false,
    instant: view.transitionSeconds === 0,
    trackObject: true,
    duration: view.transitionSeconds || undefined,
  });
  assertLease(token);
}

function columnIndex(
  header: readonly string[],
  field: string,
  layerId: string,
): number {
  const index = header.indexOf(field);
  if (index < 0) {
    throw new Error(`WWT 表格图层 ${layerId} 缺少字段 ${field}`);
  }
  return index;
}

const TABLE_FRAME_NAMES = {
  sky: "Sky",
  ecliptic: "Ecliptic",
  galactic: "Galactic",
  sun: "Sun",
  mercury: "Mercury",
  venus: "Venus",
  earth: "Earth",
  moon: "Moon",
  mars: "Mars",
  jupiter: "Jupiter",
  saturn: "Saturn",
  uranus: "Uranus",
  neptune: "Neptune",
  pluto: "Pluto",
} as const;

const TABLE_ALT_UNITS = {
  m: AltUnits.meters,
  km: AltUnits.kilometers,
  au: AltUnits.astronomicalUnits,
  pc: AltUnits.parsecs,
  kpc: AltUnits.custom,
  mpc: AltUnits.megaParsecs,
} as const;

function configureTableLayer(
  session: EngineSession,
  layer: import("@wwtelescope/engine").SpreadSheetLayer,
  spec: WwtTableLayerReview,
) {
  const header = layer.get_header();
  if (spec.coordinates.kind === "spherical") {
    layer.set_coordinatesType(CoordinatesType.spherical);
    layer.set_lngColumn(
      columnIndex(header, spec.coordinates.longitudeField, spec.layerId),
    );
    layer.set_latColumn(
      columnIndex(header, spec.coordinates.latitudeField, spec.layerId),
    );
    layer.set_raUnits(
      spec.coordinates.longitudeUnit === "hours"
        ? RAUnits.hours
        : RAUnits.degrees,
    );
    if (spec.coordinates.altitudeField !== null) {
      layer.set_altColumn(
        columnIndex(header, spec.coordinates.altitudeField, spec.layerId),
      );
    }
  } else {
    layer.set_coordinatesType(CoordinatesType.rectangular);
    layer.set_xAxisColumn(
      columnIndex(header, spec.coordinates.xField, spec.layerId),
    );
    layer.set_yAxisColumn(
      columnIndex(header, spec.coordinates.yField, spec.layerId),
    );
    layer.set_zAxisColumn(
      columnIndex(header, spec.coordinates.zField, spec.layerId),
    );
    layer.set_cartesianScale(TABLE_ALT_UNITS[spec.coordinates.xyzUnit]);
    layer.set_cartesianCustomScale(
      spec.coordinates.xyzUnit === "kpc" ? 1_000 : 1,
    );
  }
  layer.set_markerScale(
    spec.markerScale === "screen" ? MarkerScales.screen : MarkerScales.world,
  );
  layer.set_scaleFactor(spec.sizeScale);
  layer.set_opacity(spec.opacity);
  layer.set_color(session.engine.Color.fromHex(tokenColor(spec.colorToken)));
  if (spec.sizeField !== null) {
    layer.set_sizeColumn(columnIndex(header, spec.sizeField, spec.layerId));
  }
  if (spec.colorField !== null) {
    layer.set_colorMapColumn(
      columnIndex(header, spec.colorField, spec.layerId),
    );
  }
  if (spec.timeSeries !== null) {
    layer.set_timeSeries(true);
    layer.set_startDateColumn(
      columnIndex(header, spec.timeSeries.timeField, spec.layerId),
    );
    layer.set_decay(spec.timeSeries.decayDays);
  }
}

async function addTableLayer(
  session: EngineSession,
  token: symbol,
  data: ArrayBuffer,
  spec: WwtTableLayerReview,
) {
  assertLease(token);
  const text = new TextDecoder("utf-8", { fatal: true }).decode(data);
  const frame = TABLE_FRAME_NAMES[spec.coordinates.frame];
  const tabularText =
    spec.mediaType === "application/vnd.ivoa.votable+xml"
      ? session.engine.VoTable.loadFromString(text).toString()
      : text;
  const csv =
    spec.mediaType === "text/csv"
      ? tabularText
      : tabularText
          .split(/\r?\n/u)
          .map((row) =>
            row
              .split("\t")
              .map((value) => JSON.stringify(value))
              .join(","),
          )
          .join("\n");
  const layer = session.instance.lm.createSpreadsheetLayer(
    frame,
    spec.layerId,
    csv,
  );
  session.layers.add(layer);
  configureTableLayer(session, layer, spec);
}

function sceneReadback(
  session: EngineSession,
  spec: WwtSceneVisualizationReview,
): WwtSceneReadback {
  const requested = new Set(spec.readbacks);
  return {
    centerCoordinates: requested.has("center_coordinates")
      ? {
          raHours: session.instance.si.getRA(),
          decDegrees: session.instance.si.getDec(),
        }
      : null,
    fieldOfViewDegrees: requested.has("field_of_view")
      ? session.instance.ctl.renderContext.get_fovAngle()
      : null,
    cameraRollDegrees: requested.has("camera_roll")
      ? session.instance.ctl.renderContext.viewCamera.rotation
      : null,
    currentTime: requested.has("current_time")
      ? session.engine.SpaceTimeController.get_now().toISOString()
      : null,
  };
}

function waitForHold(seconds: number, signal: AbortSignal): Promise<void> {
  if (seconds <= 0) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(resolve, seconds * 1000);
    signal.addEventListener(
      "abort",
      () => {
        window.clearTimeout(timeout);
        reject(new SupersededWwtLeaseError());
      },
      { once: true },
    );
  });
}

async function playTour(
  session: EngineSession,
  token: symbol,
  spec: WwtSceneVisualizationReview,
  options: WwtSceneOptions,
  signal: AbortSignal,
) {
  do {
    for (const step of spec.tourSteps) {
      assertLease(token);
      if (step.observedAt !== null) {
        session.engine.SpaceTimeController.set_now(new Date(step.observedAt));
      }
      options.onProgress(`正在播放 WWT 场景步骤 ${step.stepId}`);
      await gotoView(session, token, step.view);
      await waitForHold(step.holdSeconds, signal);
    }
  } while (spec.tourLoop && !signal.aborted);
}

async function renderScene(
  session: EngineSession,
  token: symbol,
  spec: WwtSpec,
  options: WwtSceneOptions,
  signal: AbortSignal,
  previousSpec: WwtSpec | null,
): Promise<WwtSceneReadback | null> {
  assertLease(token);
  if (spec.mode === "fits_image") {
    resetScene(session);
    options.onProgress("正在载入 FITS 图像");
    const data = await options.loadContent(spec.contentHash);
    await addFitsLayer(session, token, data, {
      name: `FITS ${spec.sourceSnapshotId}`,
      goto: true,
      opacity: 1,
      stretch: spec.stretch,
      colorMap: spec.colorMap,
    });
    return null;
  }

  if (canUpdateSceneInPlace(previousSpec, spec)) {
    configureSceneAppearance(session, spec);
    if (previousSpec.view !== spec.view) {
      await gotoView(session, token, spec.view);
    }
    session.instance.si.clearAnnotations();
    spec.annotations.forEach((annotation) =>
      configureAnnotation(annotation, session, spec.view.fieldOfViewDegrees),
    );
    return sceneReadback(session, spec);
  }

  resetScene(session);
  configureSceneAppearance(session, spec);
  await gotoView(session, token, spec.view);
  for (const [index, fitsLayer] of spec.fitsLayers.entries()) {
    options.onProgress(
      `正在载入 FITS 图层 ${index + 1}/${spec.fitsLayers.length}`,
    );
    const data = await options.loadContent(fitsLayer.contentHash);
    await addFitsLayer(session, token, data, {
      name: fitsLayer.layerId,
      goto: false,
      opacity: fitsLayer.opacity,
      stretch: fitsLayer.stretch,
      colorMap: fitsLayer.colorMap,
      vmin: fitsLayer.vmin,
      vmax: fitsLayer.vmax,
    });
  }
  for (const [index, tableLayer] of spec.tableLayers.entries()) {
    options.onProgress(
      `正在载入表格图层 ${index + 1}/${spec.tableLayers.length}`,
    );
    const data = await options.loadContent(tableLayer.contentHash);
    await addTableLayer(session, token, data, tableLayer);
  }
  spec.annotations.forEach((annotation) =>
    configureAnnotation(annotation, session, spec.view.fieldOfViewDegrees),
  );
  const readback = sceneReadback(session, spec);
  if (spec.tourAutoplay && spec.tourSteps.length > 0) {
    void playTour(session, token, spec, options, signal).catch((error) => {
      if (error instanceof SupersededWwtLeaseError) return;
      options.onAsyncError?.(error);
    });
  }
  return readback;
}

export function openWwtSession(host: HTMLElement): WwtSessionLease {
  const token = Symbol("wwt-session-lease");
  const abortController = new AbortController();
  let previousSpec: WwtSpec | null = null;
  activeLease = token;
  const sessionPromise = getEngineSession(host);
  void sessionPromise
    .then((session) => {
      if (activeLease === token && session.canvas.parentElement !== host) {
        host.append(session.canvas);
      }
    })
    .catch(() => undefined);

  return {
    render: (spec, options) =>
      queue(async () => {
        const session = await sessionPromise;
        assertLease(token);
        if (session.canvas.parentElement !== host) host.append(session.canvas);
        try {
          const readback = await renderScene(
            session,
            token,
            spec,
            options,
            abortController.signal,
            previousSpec,
          );
          previousSpec = spec;
          return readback;
        } catch (error) {
          if (error instanceof SupersededWwtLeaseError) return null;
          if (activeLease === token) {
            previousSpec = null;
            resetScene(session);
          }
          throw error;
        }
      }),
    close: () => {
      if (activeLease !== token) return;
      abortController.abort();
      activeLease = null;
      previousSpec = null;
      void queue(async () => {
        const session = await sessionPromise;
        if (activeLease !== null) return;
        resetScene(session);
        parkingRoot(host).append(session.canvas);
      }).catch(() => undefined);
    },
  };
}
