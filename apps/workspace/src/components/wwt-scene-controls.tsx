import type { ContentHash, WwtSceneVisualizationReview } from "@xingwen/domain";
import {
  Button,
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuTrigger,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@xingwen/ui";
import { useState } from "react";

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
  const [effective, setEffective] = useState(spec);
  const [raInput, setRaInput] = useState("");
  const [decInput, setDecInput] = useState("");
  const [fovInput, setFovInput] = useState("");
  const [rateInput, setRateInput] = useState("");

  const gotoCoordinates = () => {
    const raHours = parseNumber(raInput);
    const decDegrees = parseNumber(decInput);
    const fieldOfViewDegrees = parseNumber(fovInput);
    if (
      raHours === null ||
      decDegrees === null ||
      raHours < 0 ||
      raHours > 24 ||
      decDegrees < -90 ||
      decDegrees > 90
    ) {
      return;
    }
    setEffective({
      ...effective,
      view: {
        kind: "coordinates",
        center: { raHours, decDegrees },
        fieldOfViewDegrees:
          fieldOfViewDegrees ?? effective.view.fieldOfViewDegrees,
        rollDegrees: 0,
        transitionSeconds: 1,
      },
    });
  };

  const toggleGrid = (system: (typeof GRID_SYSTEMS)[number]["system"]) => {
    const current = effective.coordinateGrids.find(
      (grid) => grid.system === system,
    );
    const coordinateGrids = current
      ? effective.coordinateGrids.filter((grid) => grid.system !== system)
      : [...effective.coordinateGrids, { system, labels: true }];
    setEffective({ ...effective, coordinateGrids });
  };

  const toggleConstellation = (
    key: (typeof CONSTELLATION_OPTIONS)[number]["key"],
  ) => {
    setEffective({
      ...effective,
      constellations: {
        ...effective.constellations,
        [key]: !effective.constellations[key],
      },
    });
  };

  const setTimeMode = (mode: string) => {
    if (mode === "system_clock") {
      setEffective({
        ...effective,
        time: { mode: "system_clock", observedAt: null, rate: null },
      });
      return;
    }
    const observedAt = effective.time.observedAt ?? new Date().toISOString();
    if (mode === "paused") {
      setEffective({
        ...effective,
        time: { mode: "paused", observedAt, rate: null },
      });
      return;
    }
    const rate = parseNumber(rateInput) ?? effective.time.rate ?? 10;
    setEffective({
      ...effective,
      time: { mode: "playback", observedAt, rate: rate === 0 ? 10 : rate },
    });
  };

  const resetScene = () => setEffective(spec);

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
        <Button
          type="button"
          variant="secondary"
          size="small"
          onClick={gotoCoordinates}
        >
          前往坐标
        </Button>
      </div>
      <div className="wwt-scene-controls__group" aria-label="场景设置">
        <Select
          value={effective.background}
          onValueChange={(value) =>
            setEffective({
              ...effective,
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
                checked={effective.coordinateGrids.some(
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
                checked={effective.constellations[option.key]}
                onCheckedChange={() => toggleConstellation(option.key)}
              >
                {option.label}
              </DropdownMenuCheckboxItem>
            ))}
            <DropdownMenuCheckboxItem
              checked={effective.precessionChart}
              onCheckedChange={() =>
                setEffective({
                  ...effective,
                  precessionChart: !effective.precessionChart,
                })
              }
            >
              岁差图
            </DropdownMenuCheckboxItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
      <div className="wwt-scene-controls__group" aria-label="时间控制">
        <Select
          value={effective.time.mode}
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
        {effective.time.mode === "playback" ? (
          <Input
            aria-label="时间倍率"
            placeholder="倍率"
            value={rateInput}
            onChange={(event) => setRateInput(event.target.value)}
            onBlur={() => setTimeMode("playback")}
          />
        ) : null}
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
