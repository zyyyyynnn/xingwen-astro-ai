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
  if (mode === "recorded") return "已记录数据";
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

const TAXONOMY_LABELS: Record<string, string> = {
  goal: "研究目标",
  research_goal: "研究目标",
  future_work: "后续研究",
  dataset: "数据集",
  field: "字段",
  source: "来源",
  paper: "论文",
  claim: "声明",
  finding: "发现",
  relation: "关系",
  reasoning_trace: "推导过程",
  evidence: "证据",
  measurement: "测量",
  method: "方法",
  limitation: "局限",
  effective_temperature: "有效温度",
  uses_dataset: "使用数据集",
  provides_field: "提供字段",
  supports_finding: "支持发现",
  cites: "引用",
  supports: "支持",
  extends: "扩展",
  derived_from: "派生自",
  limits: "限制",
  contradicts: "矛盾",
  uses_same_dataset: "使用同一数据集",
  compares_method: "比较方法",
  describes_same_system: "描述同一系统",
  consistent_with: "结果一致",
  predicts: "形成预测",
  refines_parameter: "细化参数约束",
  hypothesis: "科学假设",
  review_required: "需要人工核验",
  contradiction: "证据冲突",
  rejected: "未纳入结论",
  corrected_by_feedback: "根据反馈修正",
  structured: "结构化数据",
  source_table: "来源表格",
  document: "文档",
  emission: "发射",
  absorption: "吸收",
  sun: "太阳",
  mercury: "水星",
  venus: "金星",
  earth: "地球",
  moon: "月球",
  mars: "火星",
  jupiter: "木星",
  saturn: "土星",
  uranus: "天王星",
  neptune: "海王星",
  pluto: "冥王星",
};

export function taxonomyLabel(value: string): string {
  return TAXONOMY_LABELS[value] ?? "其他";
}

const STATUS_LABELS: Record<string, string> = {
  accepted: "已纳入结论",
  candidate: "候选观点",
  rejected: "未纳入结论",
  pending: "仍待核验",
  verified: "已核实",
  unverified: "未核实",
  failed: "失败",
  partial: "部分完成",
  supported: "有证据支持",
  unsupported: "证据不足",
  unverifiable: "无法核验",
  selected: "已选用",
  unselected: "未选用",
};

export function reviewStatusLabel(value: string): string {
  return STATUS_LABELS[value] ?? "状态待核验";
}

const COMPARABILITY_LABELS: Record<string, string> = {
  comparable: "可比较",
  incomparable: "不可比较",
  missing: "缺失",
  unresolved: "未解决",
};

export function comparabilityLabel(value: string): string {
  return COMPARABILITY_LABELS[value] ?? "尚未评估";
}

const POLARITY_LABELS: Record<string, string> = {
  positive: "正向",
  negative: "反向",
  neutral: "中性",
};

export function polarityLabel(value: string): string {
  return POLARITY_LABELS[value] ?? "方向未明确";
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
    <header className="scientific-content-header">
      <div>
        <h3>{title}</h3>
        <p>{subtitle}</p>
      </div>
      {alerts.length > 0 ? (
        <div className="scientific-content-header__alerts">{alerts}</div>
      ) : null}
    </header>
  );
}
