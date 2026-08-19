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

export function WwtSceneControls({
  spec,
  versionNumber,
  loadContent,
}: {
  readonly spec: WwtSceneVisualizationReview;
  readonly versionNumber: number;
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

  const [raInput, setRaInput] = useState("");
  const [decInput, setDecInput] = useState("");
  const [fovInput, setFovInput] = useState("");
  const [rollInput, setRollInput] = useState("");
  const [rateInput, setRateInput] = useState("");
  const [trackedTarget, setTrackedTarget] =
    useState<WwtTrackedObjectViewReview["target"]>("mars");
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
  const [observedAtInput, setObservedAtInput] = useState("");
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
    setBase({
      ...base,
      view: {
        kind: "tracked_object",
        target: trackedTarget,
        fieldOfViewDegrees: base.view.fieldOfViewDegrees,
        rollDegrees: base.view.rollDegrees,
        transitionSeconds: 1,
      },
    });
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

  const resetScene = () => {
    setBase(spec);
    setHiddenLayers([]);
    setAnnotationsHidden(false);
    setControlError(null);
  };

  return (
    <div className="wwt-scene-controls">
      <div className="wwt-scene-controls__group" aria-label="视角控制">
        <Input
          aria-label="中心赤经（小时）"
          placeholder="RA 小时"
          value={raInput}
          onChange={(event) => setRaInput(event.target.value)}
        />
        <Input
          aria-label="中心赤纬（度）"
          placeholder="Dec 度"
          value={decInput}
          onChange={(event) => setDecInput(event.target.value)}
        />
        <Input
          aria-label="视场（度）"
          placeholder="视场度"
          value={fovInput}
          onChange={(event) => setFovInput(event.target.value)}
        />
        <Input
          aria-label="相机滚转（度）"
          placeholder="滚转度"
          value={rollInput}
          onChange={(event) => setRollInput(event.target.value)}
        />
        <Button
          type="button"
          variant="secondary"
          size="small"
          onClick={gotoCoordinates}
        >
          前往坐标
        </Button>
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
          onValueChange={(value) =>
            setBase({
              ...base,
              background: value as WwtSceneVisualizationReview["background"],
            })
          }
        >
          <SelectTrigger
            aria-label="背景天图"
            className="wwt-scene-controls__select"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {BACKGROUND_OPTIONS.map((option) => (
              <SelectItem key={option.value} value={option.value}>
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
                checked={base.coordinateGrids.some(
                  (item) => item.system === grid.system,
                )}
                onCheckedChange={() => toggleGrid(grid.system)}
              >
                {grid.label}
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
                checked={base.constellations[option.key]}
                onCheckedChange={() => toggleConstellation(option.key)}
              >
                {option.label}
              </DropdownMenuCheckboxItem>
            ))}
            <DropdownMenuCheckboxItem
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
        <Select
          value={base.time.mode}
          onValueChange={(value) => setTimeMode(value)}
        >
          <SelectTrigger
            aria-label="时间模式"
            className="wwt-scene-controls__select"
          >
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
        {base.time.mode === "playback" ? (
          <Input
            aria-label="时间倍率"
            placeholder="倍率"
            value={rateInput}
            onChange={(event) => setRateInput(event.target.value)}
            onBlur={() => setTimeMode("playback")}
          />
        ) : null}
        <Input
          type="datetime-local"
          aria-label="观测时间（UTC）"
          value={observedAtInput || (base.time.observedAt?.slice(0, 16) ?? "")}
          onChange={(event) => setObservedAtInput(event.target.value)}
        />
        <Button
          type="button"
          variant="secondary"
          size="small"
          onClick={applyObservedAt}
        >
          固定观测时间（UTC）
        </Button>
        <Button type="button" variant="ghost" size="small" onClick={resetScene}>
          恢复发布场景
        </Button>
      </div>
      <WwtViewport
        spec={effective}
        versionNumber={versionNumber}
        loadContent={loadContent}
      />
    </div>
  );
}
