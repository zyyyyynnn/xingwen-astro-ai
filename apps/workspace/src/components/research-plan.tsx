import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  RunStepViewModel,
} from "@xingwen/research-adapter";
import {
  researchRunStepLabel,
  researchRunStepMessage,
} from "@xingwen/research-adapter";
import {
  AlertCircle,
  CheckCircle2,
  Circle,
  CircleSlash2,
  CircleX,
  LoaderCircle,
} from "@xingwen/ui/icons";

export type ResearchPlanItemStatus =
  | "pending"
  | "current"
  | "running"
  | "waiting"
  | "completed"
  | "failed"
  | "cancelled"
  | "skipped";

export interface ResearchPlanItem {
  readonly id: string;
  readonly label: string;
  readonly status: ResearchPlanItemStatus;
  readonly detail?: string;
}

interface ResearchPlanFacts {
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly run: ResearchRunViewModel | null;
  readonly steps: readonly RunStepViewModel[];
}

function preparationItems({
  draft,
  contract,
  run,
}: ResearchPlanFacts): readonly ResearchPlanItem[] {
  const hasBoundary = draft !== null || contract !== null || run !== null;
  return [
    {
      id: "prepare-boundary",
      label: "完善研究边界",
      status: hasBoundary ? "completed" : "current",
    },
    {
      id: "confirm-contract",
      label: "确认研究协议",
      status: contract || run ? "completed" : draft ? "current" : "pending",
    },
    {
      id: "start-run",
      label: "开始研究",
      status: run ? "completed" : contract ? "current" : "pending",
    },
  ];
}

export function createResearchPlanItems(
  facts: ResearchPlanFacts,
): readonly ResearchPlanItem[] {
  return [
    ...preparationItems(facts),
    ...facts.steps.map((step) => {
      const hasActiveDetail =
        step.status === "running" ||
        step.status === "waiting" ||
        step.status === "failed";
      return {
        id: step.id,
        label: researchRunStepLabel(step.key, step.label),
        status: step.status,
        detail: hasActiveDetail
          ? step.publicMessage?.trim() ||
            researchRunStepMessage(step.key, step.status)
          : undefined,
      };
    }),
  ];
}

export function researchPlanStatusLabel(
  status: ResearchPlanItemStatus,
): string {
  switch (status) {
    case "current":
    case "running":
      return "正在进行";
    case "waiting":
      return "等待用户";
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
  if (items.some((item) => item.status === "waiting")) return "等待用户";
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
  if (status === "failed") return <AlertCircle aria-hidden="true" />;
  if (status === "cancelled") return <CircleX aria-hidden="true" />;
  if (status === "skipped") return <CircleSlash2 aria-hidden="true" />;
  return <Circle aria-hidden="true" />;
}
