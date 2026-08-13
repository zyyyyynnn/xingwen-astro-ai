import type {
  ProjectViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  RunStepViewModel,
} from "@xingwen/research-adapter";
import {
  researchRunStatusLabel,
  researchRunStepLabel,
  researchRunStepMessage,
} from "@xingwen/research-adapter";
import type { RunStatus } from "@xingwen/domain";

export type ResearchPresentationState =
  | "empty"
  | "assistant_processing"
  | "awaiting_clarification"
  | "draft_ready"
  | "contract_confirmed"
  | "run_recorded"
  | RunStatus;

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

export interface ResearchPresentation {
  readonly state: ResearchPresentationState;
  readonly statusLabel: string;
  readonly protocolStatus: string;
  readonly planItems: readonly ResearchPlanItem[];
}

interface ResearchPresentationFacts {
  readonly project: ProjectViewModel;
  readonly entries?: readonly ResearchThreadEntryViewModel[];
  readonly draft?: ResearchContractDraftViewModel | null;
  readonly contract?: ResearchContractViewModel | null;
  readonly run?: ResearchRunViewModel | null;
  readonly steps?: readonly RunStepViewModel[];
  readonly pendingActionId?: string | null;
}

const RUN_STATES = new Set<ResearchPresentationState>([
  "queued",
  "planning",
  "fetching_data",
  "cleaning_data",
  "searching_papers",
  "summarizing_papers",
  "reasoning_literature",
  "building_graph",
  "waiting_for_input",
  "completed",
  "failed",
  "cancelled",
]);

function latestUnansweredQuestion(
  entries: readonly ResearchThreadEntryViewModel[],
): ResearchThreadEntryViewModel | null {
  const answeredQuestionIds = new Set(
    entries.flatMap((entry) =>
      entry.kind === "clarification_answer" &&
      entry.structuredPayload.answerToQuestionId
        ? [entry.structuredPayload.answerToQuestionId]
        : [],
    ),
  );
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index];
    if (
      entry?.kind === "clarification_question" &&
      !answeredQuestionIds.has(entry.structuredPayload.questionId)
    ) {
      return entry;
    }
  }
  return null;
}

function deriveState({
  project,
  entries,
  draft = null,
  contract = null,
  run = null,
  pendingActionId = null,
}: ResearchPresentationFacts): ResearchPresentationState {
  if (pendingActionId !== null) return "assistant_processing";
  const hasUnansweredClarification =
    entries === undefined
      ? project.threadSummary.hasUnansweredClarification
      : latestUnansweredQuestion(entries) !== null;
  if (hasUnansweredClarification) {
    return "awaiting_clarification";
  }

  const runStatus = run?.status ?? project.latestRunStatus;
  if (runStatus !== null) return runStatus;
  if (run !== null || project.latestRunId !== null) return "run_recorded";
  if (contract !== null || project.activeContractId !== null) {
    return "contract_confirmed";
  }
  if (draft !== null || project.activeDraftId !== null) return "draft_ready";
  const latestThreadActor =
    entries === undefined
      ? project.threadSummary.latestThreadActor
      : entries.at(-1)?.actor;
  if (latestThreadActor === "user") return "assistant_processing";
  return "empty";
}

function statusLabel(state: ResearchPresentationState): string {
  if (RUN_STATES.has(state) && state !== "run_recorded") {
    return researchRunStatusLabel(state as RunStatus);
  }
  switch (state) {
    case "assistant_processing":
      return "研究助手处理中";
    case "awaiting_clarification":
      return "等待你的回答";
    case "draft_ready":
      return "协议待确认";
    case "contract_confirmed":
      return "协议已确认";
    case "run_recorded":
      return "已有运行记录";
    default:
      return "等待研究消息";
  }
}

function preparationItems(
  state: ResearchPresentationState,
): readonly ResearchPlanItem[] {
  const hasRun = RUN_STATES.has(state) || state === "run_recorded";
  const hasContract = hasRun || state === "contract_confirmed";
  const hasDraft = hasContract || state === "draft_ready";
  return [
    {
      id: "prepare-boundary",
      label: "完善研究边界",
      status: hasDraft
        ? "completed"
        : state === "assistant_processing"
          ? "running"
          : state === "awaiting_clarification"
            ? "waiting"
            : "current",
    },
    {
      id: "confirm-contract",
      label: "确认研究协议",
      status: hasContract ? "completed" : hasDraft ? "current" : "pending",
    },
    {
      id: "start-run",
      label: "开始研究",
      status: hasRun ? "completed" : hasContract ? "current" : "pending",
    },
  ];
}

function runStepItems(
  steps: readonly RunStepViewModel[],
): readonly ResearchPlanItem[] {
  return steps.map((step) => {
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
  });
}

export function deriveResearchPresentation(
  facts: ResearchPresentationFacts,
): ResearchPresentation {
  const state = deriveState(facts);
  return {
    state,
    statusLabel: statusLabel(state),
    protocolStatus:
      facts.contract !== null && facts.contract !== undefined
        ? "已确认"
        : facts.project.activeContractId !== null
          ? "已确认"
          : facts.draft !== null && facts.draft !== undefined
            ? "草稿待确认"
            : facts.project.activeDraftId !== null
              ? "草稿待确认"
              : "待完善",
    planItems: [...preparationItems(state), ...runStepItems(facts.steps ?? [])],
  };
}
