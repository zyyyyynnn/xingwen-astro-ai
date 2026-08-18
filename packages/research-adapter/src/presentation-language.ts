import type { ExecutionMode, RunStatus } from "@xingwen/domain";
import type { RunStepStatus } from "@xingwen/domain";

const RUN_STATUS_LABELS: Readonly<Record<RunStatus, string>> = {
  queued: "已排队",
  planning: "规划研究路径",
  fetching_data: "采集研究数据",
  cleaning_data: "整理研究数据",
  acquiring_observations: "获取天文观测",
  analyzing_data: "分析科学数据",
  training_models: "训练科学模型",
  building_visualizations: "构建科学可视化",
  searching_papers: "检索相关文献",
  summarizing_papers: "归纳文献证据",
  reasoning_literature: "综合研究证据",
  building_graph: "构建证据关系",
  waiting_for_input: "等待你的回答",
  completed: "研究已完成",
  failed: "研究需要处理",
  cancelled: "研究已取消",
};

const EXECUTION_MODE_LABELS: Readonly<Record<ExecutionMode, string>> = {
  live: "真实研究",
  demo_replay: "演示回放",
};

const RUN_STEP_LABELS: Readonly<Record<string, string>> = {
  planning: "规划研究路径",
  fetching_data: "采集研究数据",
  cleaning_data: "整理研究数据",
  acquiring_observations: "获取天文观测",
  analyzing_data: "分析科学数据",
  training_models: "训练科学模型",
  building_visualizations: "构建科学可视化",
  searching_papers: "检索相关文献",
  summarizing_papers: "归纳文献证据",
  reasoning_literature: "综合研究证据",
  building_graph: "构建证据关系",
};

export function researchRunStatusLabel(status: RunStatus): string {
  return RUN_STATUS_LABELS[status];
}

export function researchExecutionModeLabel(mode: ExecutionMode): string {
  return EXECUTION_MODE_LABELS[mode];
}

export function researchRunStepLabel(key: string, fallback: string): string {
  return RUN_STEP_LABELS[key] ?? fallback;
}

export function researchRunStepMessage(
  key: string,
  status: RunStepStatus,
): string {
  const label = RUN_STEP_LABELS[key] ?? "研究步骤";
  switch (status) {
    case "completed":
      return `${label}已完成。`;
    case "running":
      return `正在${label}。`;
    case "waiting":
      return `${label}需要你的确认。`;
    case "failed":
      return `${label}遇到问题，需要处理。`;
    case "cancelled":
      return `${label}已取消。`;
    case "skipped":
      return `${label}已跳过。`;
    default:
      return `等待${label}。`;
  }
}
