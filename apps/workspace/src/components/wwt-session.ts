import type {
  ContentHash,
  FitsImageVisualizationReview,
  WwtAnnotationReview,
  WwtSceneVisualizationReview,
} from "@xingwen/domain";
import { ScaleTypes } from "@wwtelescope/engine-types";

export type WwtSpec =
  FitsImageVisualizationReview | WwtSceneVisualizationReview;

export interface WwtSceneOptions {
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
  readonly onProgress: (message: string) => void;
}

interface EngineSession {
  readonly canvas: HTMLCanvasElement;
  readonly engine: typeof import("@wwtelescope/engine");
  readonly instance: import("@wwtelescope/engine-helpers").WWTInstance;
  readonly layers: Set<import("@wwtelescope/engine").ImageSetLayer>;
  readonly objectUrls: Set<string>;
}

export interface WwtSessionLease {
  readonly render: (spec: WwtSpec, options: WwtSceneOptions) => Promise<void>;
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
  settings: {
    set_showGrid(value: boolean): boolean;
    set_showGalacticGrid(value: boolean): boolean;
    set_showEclipticGrid(value: boolean): boolean;
    set_showAltAzGrid(value: boolean): boolean;
  },
  grid: WwtSceneVisualizationReview["coordinateGrid"] | "none",
) {
  settings.set_showGrid(grid === "equatorial");
  settings.set_showGalacticGrid(grid === "galactic");
  settings.set_showEclipticGrid(grid === "ecliptic");
  settings.set_showAltAzGrid(grid === "altaz");
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
  circle.set_fill(annotation.kind === "label");
  circle.set_fillColor(color);
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
      vmin: properties.lowerCut,
      vmax: properties.upperCut,
    });
  }
}

function assertLease(token: symbol) {
  if (activeLease !== token) throw new SupersededWwtLeaseError();
}

function resetScene(session: EngineSession) {
  session.instance.si.clearAnnotations();
  configureGrid(session.instance.si.settings, "none");
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

async function renderScene(
  session: EngineSession,
  token: symbol,
  spec: WwtSpec,
  options: WwtSceneOptions,
) {
  assertLease(token);
  resetScene(session);
  if (spec.mode === "fits_image") {
    options.onProgress("正在载入 FITS 图像");
    const data = await options.loadContent(spec.contentHash);
    await addFitsLayer(session, token, data, {
      name: `FITS ${spec.sourceSnapshotId}`,
      goto: true,
      opacity: 1,
      stretch: spec.stretch,
      colorMap: spec.colorMap,
    });
    return;
  }
  if (spec.observedAt) {
    session.engine.SpaceTimeController.set_syncToClock(false);
    session.engine.SpaceTimeController.set_now(new Date(spec.observedAt));
  } else {
    session.engine.SpaceTimeController.syncTime();
  }
  const background = {
    digitized_sky_survey: "Digitized Sky Survey (Color)",
    gaia: "Gaia DR3",
    wise: "WISE All Sky (Infrared)",
    solar_system: "Solar System",
  }[spec.background];
  session.instance.setBackgroundImageByName(background);
  configureGrid(session.instance.si.settings, spec.coordinateGrid);
  await session.instance.gotoRADecZoom(
    (spec.center.raHours * Math.PI) / 12,
    (spec.center.decDegrees * Math.PI) / 180,
    spec.fieldOfViewDegrees,
    true,
  );
  assertLease(token);
  for (const fitsLayer of spec.fitsLayers) {
    options.onProgress(`正在载入 FITS 图层 ${fitsLayer.layerId}`);
    const data = await options.loadContent(fitsLayer.contentHash);
    await addFitsLayer(session, token, data, {
      name: fitsLayer.layerId,
      goto: false,
      opacity: fitsLayer.opacity,
    });
  }
  spec.annotations.forEach((annotation) =>
    configureAnnotation(annotation, session, spec.fieldOfViewDegrees),
  );
}

export function openWwtSession(host: HTMLElement): WwtSessionLease {
  const token = Symbol("wwt-session-lease");
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
          await renderScene(session, token, spec, options);
        } catch (error) {
          if (error instanceof SupersededWwtLeaseError) return;
          if (activeLease === token) resetScene(session);
          throw error;
        }
      }),
    close: () => {
      if (activeLease !== token) return;
      activeLease = null;
      void queue(async () => {
        const session = await sessionPromise;
        if (activeLease !== null) return;
        resetScene(session);
        parkingRoot(host).append(session.canvas);
      }).catch(() => undefined);
    },
  };
}
