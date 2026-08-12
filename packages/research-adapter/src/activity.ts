import type { DomainEntityId, RunEvent } from "@xingwen/domain";

export type ActivityEventKind =
  | "message"
  | "action"
  | "tool"
  | "progress"
  | "result"
  | "error"
  | "completion";

export type ActivityEventStatus = "pending" | "running" | "success" | "error";

export type ActivityOutcome =
  "pending" | "running" | "success" | "failed" | "cancelled" | "unsupported";

/** Public, domain-neutral activity data with immutable run traceability. */
export interface ActivityPresentationEvent {
  readonly id: string;
  readonly kind: ActivityEventKind;
  readonly title: string;
  readonly detail?: string;
  readonly status: ActivityEventStatus;
  readonly groupId?: string;
  readonly timestamp?: string;
  readonly runId: DomainEntityId;
  readonly sequence: number;
  readonly stepKey: DomainEntityId | null;
  readonly progress: number | null;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly outcome: ActivityOutcome;
}

type ActivityGroupScope = "none" | "run" | "step";

interface ActivityDefinition {
  readonly kind: ActivityEventKind;
  readonly title: string;
  readonly status: ActivityEventStatus;
  readonly outcome: ActivityOutcome;
  readonly groupScope: ActivityGroupScope;
}

function groupIdFor(
  event: RunEvent,
  scope: ActivityGroupScope,
): string | undefined {
  switch (scope) {
    case "none":
      return undefined;
    case "run":
      return `${event.runId}:run`;
    case "step":
      return `${event.runId}:${event.stepKey ?? "run"}`;
  }
}

function buildActivityEvent(
  event: RunEvent,
  definition: ActivityDefinition,
): ActivityPresentationEvent {
  const groupId = groupIdFor(event, definition.groupScope);
  const base = {
    id: `${event.runId}:${event.sequence}`,
    kind: definition.kind,
    title: definition.title,
    detail: localizePublicMessage(event.publicMessage),
    status: definition.status,
    timestamp: event.occurredAt,
    runId: event.runId,
    sequence: event.sequence,
    stepKey: event.stepKey,
    progress: event.progress,
    artifactVersionIds: [...event.artifactVersionIds],
    outcome: definition.outcome,
  };

  return groupId === undefined ? base : { ...base, groupId };
}

const PUBLIC_MESSAGE_TRANSLATIONS: Readonly<Record<string, string>> = {
  "Run queued": "研究运行已进入队列。",
  Planning: "正在规划研究路径。",
  "Planning data and paper acquisition": "正在规划数据与文献采集路径。",
  "Fetching data": "正在采集研究数据。",
  "Cleaning data": "正在整理研究数据。",
  "Searching papers": "正在检索相关文献。",
  "Summarizing papers": "正在归纳文献证据。",
  "Reasoning over literature": "正在综合文献证据。",
  "Building evidence graph": "正在构建证据关系。",
};

function localizePublicMessage(message: string): string {
  return PUBLIC_MESSAGE_TRANSLATIONS[message] ?? message;
}

/** Map the current exact RunEvent taxonomy; unknown types fail visibly. */
export function toActivityPresentationEvent(
  event: RunEvent,
): ActivityPresentationEvent {
  switch (event.eventType) {
    case "run.queued":
      return buildActivityEvent(event, {
        kind: "message",
        title: "研究已排队",
        status: "pending",
        outcome: "pending",
        groupScope: "none",
      });
    case "run.planning":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "规划研究路径",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.fetching_data":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "采集研究数据",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.cleaning_data":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "整理研究数据",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.searching_papers":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "检索相关文献",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.summarizing_papers":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "归纳文献证据",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.reasoning_literature":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "综合研究证据",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "run.building_graph":
      return buildActivityEvent(event, {
        kind: "progress",
        title: "构建证据关系",
        status: "running",
        outcome: "running",
        groupScope: "run",
      });
    case "step.started":
      return buildActivityEvent(event, {
        kind: "action",
        title: "开始执行步骤",
        status: "running",
        outcome: "running",
        groupScope: "step",
      });
    case "step.retry_scheduled":
      return buildActivityEvent(event, {
        kind: "action",
        title: "步骤等待重试",
        status: "pending",
        outcome: "pending",
        groupScope: "step",
      });
    case "step.completed":
      return buildActivityEvent(event, {
        kind: "result",
        title: "步骤已完成",
        status: "success",
        outcome: "success",
        groupScope: "step",
      });
    case "run.completed":
      return buildActivityEvent(event, {
        kind: "completion",
        title: "研究已完成",
        status: "success",
        outcome: "success",
        groupScope: "none",
      });
    case "run.failed":
      return buildActivityEvent(event, {
        kind: "error",
        title: "研究运行失败",
        status: "error",
        outcome: "failed",
        groupScope: "none",
      });
    case "run.cancelled":
      return buildActivityEvent(event, {
        kind: "error",
        title: "研究已取消",
        status: "error",
        outcome: "cancelled",
        groupScope: "none",
      });
    default:
      return buildActivityEvent(event, {
        kind: "error",
        title: "暂无法显示此运行事件",
        status: "error",
        outcome: "unsupported",
        groupScope: "none",
      });
  }
}
