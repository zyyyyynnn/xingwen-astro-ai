import type { ReactNode } from "react";

export type ScientificContentSurface = "fullscreen";

export const SURFACE_LIMITS: Record<ScientificContentSurface, number> = {
  fullscreen: 80,
};

export function valueOrUnavailable(
  value: string | number | null | undefined,
): string {
  if (value === null || value === undefined || String(value).trim() === "") {
    return "未提供";
  }
  return String(value);
}

export function sourceModeLabel(mode: string): string {
  if (mode === "live") return "实时数据";
  if (mode === "cached") return "缓存数据";
  if (mode === "fixture") return "演示数据";
  return "来源状态未知";
}

export function formatNumber(
  value: number | null | undefined,
  digits = 4,
): string {
  return value === null || value === undefined || !Number.isFinite(value)
    ? "未提供"
    : value.toFixed(digits);
}

export function limitNote(
  total: number,
  shown: number,
  unit: string,
): string | null {
  return total > shown ? `当前显示前 ${shown} / ${total} ${unit}。` : null;
}

/** Render internal snake_case tokens as readable words instead of raw enums. */
export function humanizeToken(value: string): string {
  return value.replaceAll("_", " ");
}

const TAXONOMY_LABELS: Record<string, string> = {
  research_goal: "研究目标",
  dataset: "数据集",
  field: "字段",
  paper: "论文",
  claim: "声明",
  finding: "发现",
  measurement: "测量",
  method: "方法",
  limitation: "局限",
  uses_dataset: "使用数据集",
  provides_field: "提供字段",
  supports_finding: "支持发现",
  supports: "支持",
  extends: "扩展",
  derived_from: "派生自",
  limits: "限制",
  contradicts: "矛盾",
  uses_same_dataset: "使用同一数据集",
  compares_method: "比较方法",
};

export function taxonomyLabel(value: string): string {
  return TAXONOMY_LABELS[value] ?? humanizeToken(value);
}

const STATUS_LABELS: Record<string, string> = {
  accepted: "已接受",
  rejected: "已拒绝",
  pending: "待处理",
  verified: "已核实",
  unverified: "未核实",
  failed: "失败",
  partial: "部分完成",
};

export function reviewStatusLabel(value: string): string {
  return STATUS_LABELS[value] ?? humanizeToken(value);
}

const COMPARABILITY_LABELS: Record<string, string> = {
  comparable: "可比较",
  incomparable: "不可比较",
  missing: "缺失",
  unresolved: "未解决",
};

export function comparabilityLabel(value: string): string {
  return COMPARABILITY_LABELS[value] ?? humanizeToken(value);
}

const POLARITY_LABELS: Record<string, string> = {
  positive: "正向",
  negative: "反向",
  neutral: "中性",
};

export function polarityLabel(value: string): string {
  return POLARITY_LABELS[value] ?? humanizeToken(value);
}

export function ScientificContentHeader({
  title,
  subtitle,
  alerts = [],
}: {
  readonly title: string;
  readonly subtitle: string;
  /** Only user-facing anomaly states (failures, warnings, partial results). */
  readonly alerts?: readonly ReactNode[];
}) {
  return (
    <header className="scientific-artifact__header mb-2 flex items-start justify-between gap-2">
      <div>
        <h3 className="text-sm font-semibold text-[var(--oh-foreground)]">
          {title}
        </h3>
        <p className="text-xs text-[var(--oh-muted)] mt-0.5">{subtitle}</p>
      </div>
      {alerts.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">{alerts}</div>
      ) : null}
    </header>
  );
}
