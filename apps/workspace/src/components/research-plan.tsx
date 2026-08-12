import {
  AlertCircle,
  CheckCircle2,
  Circle,
  CircleSlash2,
  CircleX,
  LoaderCircle,
  TriangleAlert,
} from "@xingwen/ui/icons";
import type {
  ResearchPlanItem,
  ResearchPlanItemStatus,
} from "../presentation/research-presentation";

export function researchPlanStatusLabel(
  status: ResearchPlanItemStatus,
): string {
  switch (status) {
    case "current":
    case "running":
      return "正在进行";
    case "waiting":
      return "等待你的回答";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    case "skipped":
      return "已跳过";
    default:
      return "待开始";
  }
}

export function researchPlanSummary(
  items: readonly ResearchPlanItem[],
): string {
  if (items.some((item) => item.status === "failed")) return "需要处理";
  if (items.some((item) => item.status === "cancelled")) return "已取消";
  if (items.some((item) => item.status === "waiting")) return "等待你的回答";
  if (
    items.some((item) => item.status === "running" || item.status === "current")
  ) {
    return "正在进行";
  }
  if (
    items.every(
      (item) => item.status === "completed" || item.status === "skipped",
    )
  ) {
    return "已完成";
  }
  return "待开始";
}

export function ResearchPlanStatusIcon({
  status,
}: {
  readonly status: ResearchPlanItemStatus;
}) {
  if (status === "completed") return <CheckCircle2 aria-hidden="true" />;
  if (status === "current" || status === "running") {
    return (
      <LoaderCircle
        className="animate-spin motion-reduce:animate-none"
        aria-hidden="true"
      />
    );
  }
  if (status === "waiting") return <AlertCircle aria-hidden="true" />;
  if (status === "failed") return <TriangleAlert aria-hidden="true" />;
  if (status === "cancelled") return <CircleX aria-hidden="true" />;
  if (status === "skipped") return <CircleSlash2 aria-hidden="true" />;
  return <Circle aria-hidden="true" />;
}
