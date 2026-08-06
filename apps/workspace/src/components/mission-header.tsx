import type {
  ResearchContract,
  ResearchProject,
  ResearchRun,
  RunStatus,
} from "@xingwen/domain";

export interface MissionHeaderProps {
  readonly project: ResearchProject | null;
  readonly contract: ResearchContract | null;
  readonly run: ResearchRun | null;
  readonly onPrimaryAction?: () => void;
  readonly primaryActionLabel?: string;
  readonly primaryActionDisabled?: boolean;
}

function runStatusLabel(status: RunStatus | null): string {
  if (!status) return "未启动";
  switch (status) {
    case "queued":
      return "排队中";
    case "planning":
      return "规划中";
    case "fetching_data":
      return "采集数据";
    case "cleaning_data":
      return "清洗数据";
    case "searching_papers":
      return "检索论文";
    case "summarizing_papers":
      return "总结论文";
    case "reasoning_literature":
      return "文献推理";
    case "building_graph":
      return "构建图谱";
    case "waiting_for_input":
      return "待复核";
    case "completed":
      return "已完成";
    case "failed":
      return "失败";
    case "cancelled":
      return "已取消";
    default:
      return status;
  }
}

interface DerivedAction {
  readonly label: string;
  readonly available: boolean;
}

function deriveActionFromRun(run: ResearchRun | null): DerivedAction {
  if (!run) return { label: "启动运行", available: true };
  switch (run.status) {
    case "completed":
      return { label: "查看总结", available: true };
    case "failed":
    case "cancelled":
      return { label: "重试运行", available: true };
    case "waiting_for_input":
      return { label: "处理待复核", available: true };
    case "queued":
    case "planning":
    case "fetching_data":
    case "cleaning_data":
    case "searching_papers":
    case "summarizing_papers":
    case "reasoning_literature":
    case "building_graph":
      return { label: "查看进度", available: true };
    default:
      return { label: "启动运行", available: true };
  }
}

/** Mission header: project title, research goal, status and primary action. */
export function MissionHeader({
  project,
  contract,
  run,
  onPrimaryAction,
  primaryActionLabel,
  primaryActionDisabled = false,
}: MissionHeaderProps) {
  const derived = deriveActionFromRun(run);
  const actionLabel = primaryActionLabel ?? derived.label;
  const actionDisabled = primaryActionDisabled || !derived.available;

  return (
    <header className="mission-header" aria-label="研究使命">
      <h2 className="mission-header__title">
        研究使命：{project?.name ?? "未选择项目"}
      </h2>
      <p className="mission-header__goal">
        研究目标：{contract?.researchGoal ?? "尚无已确认 Contract"}
      </p>
      <div className="mission-header__status-row">
        <span
          className="mission-header__status"
          data-run-status={run?.status ?? "idle"}
        >
          {runStatusLabel(run?.status ?? null)}
        </span>
        {run ? (
          <span className="mission-header__progress">进度 {run.progress}%</span>
        ) : null}
        {run ? (
          <span className="mission-header__execution">
            执行：{run.executionMode}
          </span>
        ) : null}
        {onPrimaryAction ? (
          <button
            type="button"
            className="mission-header__action"
            onClick={onPrimaryAction}
            disabled={actionDisabled}
          >
            {actionLabel}
          </button>
        ) : null}
      </div>
    </header>
  );
}
