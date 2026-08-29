import type {
  ContentHash,
  WwtSceneVisualizationReview,
  WwtTrackedObjectViewReview,
} from "@xingwen/domain";
import {
  Button,
  Checkbox,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
  Field,
  FieldLabel,
  Input,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@xingwen/ui";
import { useMemo, useState } from "react";

import { WwtViewport } from "./wwt-viewport";

const BACKGROUND_OPTIONS = [
  { value: "digitized_sky_survey", label: "数字化巡天" },
  { value: "gaia", label: "Gaia DR3" },
  { value: "wise", label: "WISE 红外全天" },
  { value: "solar_system", label: "太阳系" },
] as const;

const GRID_SYSTEMS = [
  { system: "equatorial", label: "赤道网格" },
  { system: "galactic", label: "银道网格" },
  { system: "ecliptic", label: "黄道网格" },
  { system: "altaz", label: "地平网格" },
] as const;

const CONSTELLATION_OPTIONS = [
  { key: "boundaries", label: "星座边界" },
  { key: "figures", label: "星座连线" },
  { key: "pictures", label: "星座图像" },
  { key: "labels", label: "星座名称" },
] as const;

const TIME_MODE_LABELS: Record<string, string> = {
  system_clock: "跟随系统时钟",
  paused: "固定观测时间",
  playback: "时间回放",
};

const TRACKED_TARGETS: readonly {
  readonly value: WwtTrackedObjectViewReview["target"];
  readonly label: string;
}[] = [
  { value: "sun", label: "太阳" },
  { value: "mercury", label: "水星" },
  { value: "venus", label: "金星" },
  { value: "earth", label: "地球" },
  { value: "moon", label: "月球" },
  { value: "mars", label: "火星" },
  { value: "jupiter", label: "木星" },
  { value: "saturn", label: "土星" },
  { value: "uranus", label: "天王星" },
  { value: "neptune", label: "海王星" },
  { value: "pluto", label: "冥王星" },
];

function parseNumber(value: string): number | null {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

const EMPTY_CONSTELLATIONS: WwtSceneVisualizationReview["constellations"] = {
  boundaries: false,
  figures: false,
  pictures: false,
  labels: false,
};

export function normalizeSolarSystemScene(
  scene: WwtSceneVisualizationReview,
): WwtSceneVisualizationReview {
  return {
    ...scene,
    background: "solar_system",
    foreground: null,
    constellations: EMPTY_CONSTELLATIONS,
    precessionChart: false,
  };
}

export function transitionSceneBackground(
  scene: WwtSceneVisualizationReview,
  background: WwtSceneVisualizationReview["background"],
): WwtSceneVisualizationReview {
  return background === "solar_system"
    ? normalizeSolarSystemScene(scene)
    : { ...scene, background };
}

export function transitionToTrackedObject(
  scene: WwtSceneVisualizationReview,
  target: WwtTrackedObjectViewReview["target"],
): WwtSceneVisualizationReview {
  return normalizeSolarSystemScene({
    ...scene,
    view: {
      kind: "tracked_object",
      target,
      fieldOfViewDegrees: scene.view.fieldOfViewDegrees,
      rollDegrees: scene.view.rollDegrees,
      transitionSeconds: 1,
    },
  });
}

export function WwtSceneControls({
  spec,
  loadContent,
}: {
  readonly spec: WwtSceneVisualizationReview;
  readonly loadContent: (contentHash: ContentHash) => Promise<ArrayBuffer>;
}) {
  const [base, setBase] = useState(spec);
  const [hiddenLayers, setHiddenLayers] = useState<readonly string[]>([]);
  const [annotationsHidden, setAnnotationsHidden] = useState(false);

  const effective = useMemo<WwtSceneVisualizationReview>(() => {
    if (hiddenLayers.length === 0 && !annotationsHidden) {
      return base;
    }
    const hidden = new Set(hiddenLayers);
    return {
      ...base,
      fitsLayers: base.fitsLayers.map((layer) =>
        hidden.has(layer.layerId) ? { ...layer, opacity: 0 } : layer,
      ),
      tableLayers: base.tableLayers.map((layer) =>
        hidden.has(layer.layerId) ? { ...layer, opacity: 0 } : layer,
      ),
      annotations: annotationsHidden ? [] : base.annotations,
    };
  }, [base, hiddenLayers, annotationsHidden]);

  // Local control drafts start from the published immutable spec so the
  // controls describe the scene the user is actually viewing.
  const [raInput, setRaInput] = useState(
    spec.view.kind === "coordinates" ? String(spec.view.center.raHours) : "",
  );
  const [decInput, setDecInput] = useState(
    spec.view.kind === "coordinates" ? String(spec.view.center.decDegrees) : "",
  );
  const [fovInput, setFovInput] = useState(
    String(spec.view.fieldOfViewDegrees),
  );
  const [rollInput, setRollInput] = useState(String(spec.view.rollDegrees));
  const [rateInput, setRateInput] = useState(
    spec.time.rate === null ? "" : String(spec.time.rate),
  );
  const [trackedTarget, setTrackedTarget] = useState<
    WwtTrackedObjectViewReview["target"]
  >(spec.view.kind === "tracked_object" ? spec.view.target : "mars");
  const [latitudeInput, setLatitudeInput] = useState(
    () => spec.observer?.latitudeDegrees.toString() ?? "0",
  );
  const [longitudeInput, setLongitudeInput] = useState(
    () => spec.observer?.longitudeDegrees.toString() ?? "0",
  );
  const [elevationInput, setElevationInput] = useState(
    () => spec.observer?.elevationMeters.toString() ?? "0",
  );
  const [localHorizonMode, setLocalHorizonMode] = useState(
    () => spec.observer?.localHorizonMode ?? false,
  );
  const [observedAtInput, setObservedAtInput] = useState(
    spec.time.observedAt?.slice(0, 16) ?? "",
  );
  const [controlError, setControlError] = useState<string | null>(null);

  const gotoCoordinates = () => {
    const raHours = parseNumber(raInput);
    const decDegrees = parseNumber(decInput);
    const fieldOfViewDegrees =
      fovInput.trim() === "" ? null : parseNumber(fovInput);
    if (raHours === null || raHours < 0 || raHours > 24) {
      setControlError("赤经必须是 0–24 之间的数值（小时）。");
      return;
    }
    if (decDegrees === null || decDegrees < -90 || decDegrees > 90) {
      setControlError("赤纬必须是 -90 到 90 之间的数值（度）。");
      return;
    }
    if (
      fieldOfViewDegrees !== null &&
      (fieldOfViewDegrees <= 0 || fieldOfViewDegrees > 180)
    ) {
      setControlError("视场必须是 0–180 之间的数值（度）。");
      return;
    }
    // Empty roll input keeps the current scene roll; only an explicit value
    // changes the camera roll.
    const rollDegrees =
      rollInput.trim() === "" ? base.view.rollDegrees : parseNumber(rollInput);
    if (rollDegrees === null || rollDegrees < -180 || rollDegrees > 180) {
      setControlError("相机滚转必须是 -180 到 180 之间的数值（度）。");
      return;
    }
    setControlError(null);
    setBase({
      ...base,
      view: {
        kind: "coordinates",
        center: { raHours, decDegrees },
        fieldOfViewDegrees: fieldOfViewDegrees ?? base.view.fieldOfViewDegrees,
        rollDegrees,
        transitionSeconds: 1,
      },
    });
  };

  const trackObject = () => {
    setControlError(null);
    setBase((current) => transitionToTrackedObject(current, trackedTarget));
  };

  const applyObserver = () => {
    const latitudeDegrees = parseNumber(latitudeInput);
    const longitudeDegrees = parseNumber(longitudeInput);
    const elevationMeters = parseNumber(elevationInput);
    if (
      latitudeDegrees === null ||
      latitudeDegrees < -90 ||
      latitudeDegrees > 90
    ) {
      setControlError("观测点纬度必须是 -90 到 90 之间的数值（度）。");
      return;
    }
    if (
      longitudeDegrees === null ||
      longitudeDegrees < -180 ||
      longitudeDegrees > 180
    ) {
      setControlError("观测点经度必须是 -180 到 180 之间的数值（度）。");
      return;
    }
    if (
      elevationMeters === null ||
      elevationMeters < -500 ||
      elevationMeters > 100000
    ) {
      setControlError("观测点海拔必须是 -500 到 100000 之间的数值（米）。");
      return;
    }
    setControlError(null);
    setBase({
      ...base,
      observer: {
        latitudeDegrees,
        longitudeDegrees,
        elevationMeters,
        localHorizonMode,
      },
    });
  };

  const applyObservedAt = () => {
    if (!observedAtInput) {
      setControlError("请填写观测时间（UTC）。");
      return;
    }
    // The input is declared UTC in the UI; serialize it as ISO UTC instead of
    // letting the local machine timezone define the scientific time scale.
    const parsed = new Date(`${observedAtInput}Z`);
    if (Number.isNaN(parsed.getTime())) {
      setControlError("观测时间（UTC）格式无效。");
      return;
    }
    setControlError(null);
    setBase({
      ...base,
      time: { mode: "paused", observedAt: parsed.toISOString(), rate: null },
    });
  };

  const toggleGrid = (system: (typeof GRID_SYSTEMS)[number]["system"]) => {
    if (system === "altaz" && base.observer === null) return;
    const current = base.coordinateGrids.find((grid) => grid.system === system);
    const coordinateGrids = current
      ? base.coordinateGrids.filter((grid) => grid.system !== system)
      : [...base.coordinateGrids, { system, labels: true }];
    setBase({ ...base, coordinateGrids });
  };

  const toggleConstellation = (
    key: (typeof CONSTELLATION_OPTIONS)[number]["key"],
  ) => {
    setBase({
      ...base,
      constellations: {
        ...base.constellations,
        [key]: !base.constellations[key],
      },
    });
  };

  const toggleLayer = (layerId: string) => {
    setHiddenLayers((current) =>
      current.includes(layerId)
        ? current.filter((item) => item !== layerId)
        : [...current, layerId],
    );
  };

  const setTimeMode = (mode: string) => {
    if (mode === "system_clock") {
      setControlError(null);
      setBase({
        ...base,
        time: { mode: "system_clock", observedAt: null, rate: null },
      });
      return;
    }
    const observedAt = base.time.observedAt ?? new Date().toISOString();
    if (mode === "paused") {
      setBase({
        ...base,
        time: { mode: "paused", observedAt, rate: null },
      });
      return;
    }
    const rate = parseNumber(rateInput) ?? base.time.rate ?? 10;
    setBase({
      ...base,
      time: { mode: "playback", observedAt, rate: rate === 0 ? 10 : rate },
    });
  };

  const toggleTour = () => {
    setBase({ ...base, tourAutoplay: !base.tourAutoplay });
  };

  // “恢复发布场景” must return both the rendered WWT scene and every control
  // draft to the published ArtifactVersion spec, so no exploration state from
  // the previous scene leaks into the reset view.
  const resetScene = () => {
    setBase(spec);
    setHiddenLayers([]);
    setAnnotationsHidden(false);
    setControlError(null);
    setRaInput(
      spec.view.kind === "coordinates" ? String(spec.view.center.raHours) : "",
    );
    setDecInput(
      spec.view.kind === "coordinates"
        ? String(spec.view.center.decDegrees)
        : "",
    );
    setFovInput(String(spec.view.fieldOfViewDegrees));
    setRollInput(String(spec.view.rollDegrees));
    setRateInput(spec.time.rate === null ? "" : String(spec.time.rate));
    setTrackedTarget(
      spec.view.kind === "tracked_object" ? spec.view.target : "mars",
    );
    setLatitudeInput(spec.observer?.latitudeDegrees.toString() ?? "0");
    setLongitudeInput(spec.observer?.longitudeDegrees.toString() ?? "0");
    setElevationInput(spec.observer?.elevationMeters.toString() ?? "0");
    setLocalHorizonMode(spec.observer?.localHorizonMode ?? false);
    setObservedAtInput(spec.time.observedAt?.slice(0, 16) ?? "");
  };

  return (
    <div className="wwt-scene-controls">
      <div className="wwt-scene-controls__group" aria-label="视角控制">
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" variant="secondary" size="small">
              定位与视角
            </Button>
          </PopoverTrigger>
          <PopoverContent className="wwt-scene-controls__coordinate-panel">
            <Field>
              <FieldLabel htmlFor="wwt-ra">中心赤经（小时）</FieldLabel>
              <Input
                id="wwt-ra"
                value={raInput}
                onChange={(event) => setRaInput(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="wwt-dec">中心赤纬（度）</FieldLabel>
              <Input
                id="wwt-dec"
                value={decInput}
                onChange={(event) => setDecInput(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="wwt-fov">视场（度）</FieldLabel>
              <Input
                id="wwt-fov"
                value={fovInput}
                onChange={(event) => setFovInput(event.target.value)}
              />
            </Field>
            <Field>
              <FieldLabel htmlFor="wwt-roll">相机滚转（度）</FieldLabel>
              <Input
                id="wwt-roll"
                value={rollInput}
                onChange={(event) => setRollInput(event.target.value)}
              />
            </Field>
            <Button
              type="button"
              variant="primary"
              size="small"
              onClick={gotoCoordinates}
            >
              前往坐标
            </Button>
          </PopoverContent>
        </Popover>
        <Select
          value={trackedTarget}
          onValueChange={(value) =>
            setTrackedTarget(value as WwtTrackedObjectViewReview["target"])
          }
        >
          <SelectTrigger
            aria-label="跟踪天体"
            className="wwt-scene-controls__select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {TRACKED_TARGETS.map((target) => (
              <SelectItem key={target.value} value={target.value}>
                {target.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          type="button"
          variant="secondary"
          size="small"
          onClick={trackObject}
        >
          跟踪天体
        </Button>
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" variant="secondary" size="small">
              观测点
            </Button>
          </PopoverTrigger>
          <PopoverContent className="wwt-scene-controls__observer">
            <Input
              aria-label="观测点纬度（度）"
              placeholder="纬度度"
              value={latitudeInput}
              onChange={(event) => setLatitudeInput(event.target.value)}
            />
            <Input
              aria-label="观测点经度（度）"
              placeholder="经度度"
              value={longitudeInput}
              onChange={(event) => setLongitudeInput(event.target.value)}
            />
            <Input
              aria-label="观测点海拔（米）"
              placeholder="海拔米"
              value={elevationInput}
              onChange={(event) => setElevationInput(event.target.value)}
            />
            <label className="wwt-scene-controls__observer-horizon">
              <Checkbox
                checked={localHorizonMode}
                onCheckedChange={(value) => setLocalHorizonMode(value === true)}
              />
              <span>使用本地地平坐标系</span>
            </label>
            <Button
              type="button"
              variant="secondary"
              size="small"
              onClick={applyObserver}
            >
              应用观测点
            </Button>
          </PopoverContent>
        </Popover>
      </div>
      {controlError ? (
        <p className="wwt-scene-controls__error" role="alert">
          {controlError}
        </p>
      ) : null}
      <div className="wwt-scene-controls__group" aria-label="场景设置">
        <Select
          value={base.background}
          onValueChange={(value) => {
            setControlError(null);
            setBase((current) =>
              transitionSceneBackground(
                current,
                value as WwtSceneVisualizationReview["background"],
              ),
            );
          }}
        >
          <SelectTrigger
            aria-label="背景天图"
            className="wwt-scene-controls__select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BACKGROUND_OPTIONS.map((option) => (
              <SelectItem
                key={option.value}
                value={option.value}
                disabled={
                  base.view.kind === "tracked_object" &&
                  option.value !== "solar_system"
                }
              >
                {option.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="secondary" size="small">
              坐标网格
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {GRID_SYSTEMS.map((grid) => (
              <DropdownMenuCheckboxItem
                key={grid.system}
                disabled={grid.system === "altaz" && base.observer === null}
                checked={base.coordinateGrids.some(
                  (item) => item.system === grid.system,
                )}
                onCheckedChange={() => toggleGrid(grid.system)}
              >
                {grid.system === "altaz" && base.observer === null
                  ? `${grid.label}（需先设置观测点）`
                  : grid.label}
              </DropdownMenuCheckboxItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button type="button" variant="secondary" size="small">
              星座叠加
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent>
            {CONSTELLATION_OPTIONS.map((option) => (
              <DropdownMenuCheckboxItem
                key={option.key}
                disabled={base.background === "solar_system"}
                checked={base.constellations[option.key]}
                onCheckedChange={() => toggleConstellation(option.key)}
              >
                {option.label}
              </DropdownMenuCheckboxItem>
            ))}
            <DropdownMenuCheckboxItem
              disabled={base.background === "solar_system"}
              checked={base.precessionChart}
              onCheckedChange={() =>
                setBase({
                  ...base,
                  precessionChart: !base.precessionChart,
                })
              }
            >
              岁差图
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>
        {base.fitsLayers.length > 0 || base.tableLayers.length > 0 ? (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button type="button" variant="secondary" size="small">
                图层
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent>
              {base.fitsLayers.map((layer, index) => (
                <DropdownMenuCheckboxItem
                  key={layer.layerId}
                  checked={!hiddenLayers.includes(layer.layerId)}
                  onCheckedChange={() => toggleLayer(layer.layerId)}
                >
                  {`FITS 图层 ${index + 1}`}
                </DropdownMenuCheckboxItem>
              ))}
              {base.tableLayers.map((layer, index) => (
                <DropdownMenuCheckboxItem
                  key={layer.layerId}
                  checked={!hiddenLayers.includes(layer.layerId)}
                  onCheckedChange={() => toggleLayer(layer.layerId)}
                >
                  {`表格图层 ${index + 1}`}
                </DropdownMenuCheckboxItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        ) : null}
        {base.annotations.length > 0 ? (
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={() => setAnnotationsHidden((value) => !value)}
          >
            {annotationsHidden ? "显示标注" : "隐藏标注"}
          </Button>
        ) : null}
        {base.tourSteps.length > 0 ? (
          <Button
            type="button"
            variant="secondary"
            size="small"
            onClick={toggleTour}
          >
            {base.tourAutoplay ? "停止巡览" : "播放巡览"}
          </Button>
        ) : null}
      </div>
      <div className="wwt-scene-controls__group" aria-label="时间控制">
        <Popover>
          <PopoverTrigger asChild>
            <Button type="button" variant="secondary" size="small">
              时间设置
            </Button>
          </PopoverTrigger>
          <PopoverContent className="wwt-scene-controls__time-panel">
            <Field>
              <FieldLabel>时间模式</FieldLabel>
              <Select
                value={base.time.mode}
                onValueChange={(value) => setTimeMode(value)}
              >
                <SelectTrigger aria-label="时间模式">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(TIME_MODE_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            {base.time.mode === "playback" ? (
              <Field>
                <FieldLabel htmlFor="wwt-time-rate">时间倍率</FieldLabel>
                <Input
                  id="wwt-time-rate"
                  value={rateInput}
                  onChange={(event) => setRateInput(event.target.value)}
                  onBlur={() => setTimeMode("playback")}
                />
              </Field>
            ) : null}
            <Field>
              <FieldLabel htmlFor="wwt-observed-at">观测时间（UTC）</FieldLabel>
              <Input
                id="wwt-observed-at"
                type="datetime-local"
                value={
                  observedAtInput || (base.time.observedAt?.slice(0, 16) ?? "")
                }
                onChange={(event) => setObservedAtInput(event.target.value)}
              />
            </Field>
            <Button
              type="button"
              variant="primary"
              size="small"
              onClick={applyObservedAt}
            >
              固定观测时间
            </Button>
          </PopoverContent>
        </Popover>
        <Button type="button" variant="ghost" size="small" onClick={resetScene}>
          恢复发布场景
        </Button>
      </div>
      <WwtViewport spec={effective} loadContent={loadContent} />
    </div>
  );
}
