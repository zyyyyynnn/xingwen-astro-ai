import type {
  DomainEntityId,
  RepairCheckpointContext,
  RepairDecisionInput,
  RepairOutcome,
} from "@xingwen/domain";

import type { ActivityPresentationEvent } from "./activity";
import { mergeActivityPresentationEvents } from "./activity";
import type {
  ProjectViewModel,
  ResearchArtifactViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
  ResearchThreadEntryViewModel,
  RunCheckpointViewModel,
  RunStepViewModel,
} from "./view-model";

export interface UserMessageStreamItem {
  readonly id: string;
  readonly kind: "user_message";
  readonly message: string;
  readonly timestamp: string;
}

export interface AssistantReasoningStreamItem {
  readonly id: string;
  readonly kind: "assistant_reasoning";
  readonly content: string;
  readonly isStreaming: boolean;
  readonly timestamp: string;
}

export interface AssistantMessageStreamItem {
  readonly id: string;
  readonly kind: "assistant_message";
  readonly message: string;
  readonly outcome: string | null;
  readonly timestamp: string;
}

export interface ClarificationQuestionStreamItem {
  readonly id: string;
  readonly kind: "clarification_question";
  readonly questionId: string;
  readonly question: string;
  readonly options: readonly string[];
  readonly answered: boolean;
  readonly selectedOption: string | null;
  readonly timestamp: string;
}

export interface CheckpointPromptStreamItem {
  readonly id: string;
  readonly kind: "checkpoint_prompt";
  readonly checkpointId: string;
  readonly runId: string;
  readonly runRevision: number;
  readonly question: string;
  readonly options: readonly string[];
  readonly checkpointKind: "choice" | "scientific_repair";
  readonly repairContext: RepairCheckpointContext | null;
  readonly answered: boolean;
  readonly selectedOption: string | null;
  readonly freeText: string | null;
  readonly repairDecisions: readonly RepairDecisionInput[];
  readonly repairOutcome: RepairOutcome | null;
  readonly timestamp: string;
}

export interface ProtocolDraftStreamItem {
  readonly id: string;
  readonly kind: "protocol_draft";
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly isConfirmed: boolean;
  readonly runStatusLabel: string | null;
  readonly timestamp: string;
}

export interface ToolExecutionStreamItem {
  readonly id: string;
  readonly kind: "tool_execution";
  readonly event: ActivityPresentationEvent;
  readonly timestamp: string;
}

export interface ArtifactResultStreamItem {
  readonly id: string;
  readonly kind: "artifact_result";
  readonly artifact: ResearchArtifactViewModel;
  readonly versionId: DomainEntityId;
  readonly title: string;
  readonly summary: string | null;
  readonly timestamp: string;
}

export interface RunStepProgressStreamItem {
  readonly id: string;
  readonly kind: "step_progress";
  readonly currentStep: number;
  readonly totalSteps: number;
  readonly stepLabel: string;
  readonly artifactsCount: number;
  readonly status: "running" | "completed" | "error";
  readonly timestamp: string;
}

export type WorkspaceStreamItem =
  | UserMessageStreamItem
  | AssistantReasoningStreamItem
  | AssistantMessageStreamItem
  | ClarificationQuestionStreamItem
  | CheckpointPromptStreamItem
  | ProtocolDraftStreamItem
  | ToolExecutionStreamItem
  | ArtifactResultStreamItem
  | RunStepProgressStreamItem;

export interface UnifiedStreamInput {
  readonly project: ProjectViewModel;
  readonly entries: readonly ResearchThreadEntryViewModel[];
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly run: ResearchRunViewModel | null;
  readonly steps?: readonly RunStepViewModel[];
  readonly events: readonly ActivityPresentationEvent[];
  readonly artifacts: readonly ResearchArtifactViewModel[];
  /**
   * Version→Artifact links resolved from real server ArtifactVersion
   * metadata. Result placement never compares an Artifact id with an
   * ArtifactVersion id.
   */
  readonly artifactVersionLinks?: ReadonlyMap<string, string>;
  readonly checkpoint?: RunCheckpointViewModel | null;
  readonly pendingUserMessage?: string | null;
}

interface SortableStreamEntry {
  readonly item: WorkspaceStreamItem;
  readonly timestamp: string;
  readonly sourceRank: number;
  readonly sequence: number;
  readonly tieId: string;
}

function compareSortableEntries(
  a: SortableStreamEntry,
  b: SortableStreamEntry,
): number {
  const timeA = Date.parse(a.timestamp);
  const timeB = Date.parse(b.timestamp);
  if (!Number.isNaN(timeA) && !Number.isNaN(timeB) && timeA !== timeB) {
    return timeA - timeB;
  }
  if (a.sourceRank !== b.sourceRank) {
    return a.sourceRank - b.sourceRank;
  }
  if (a.sequence !== b.sequence) {
    return a.sequence - b.sequence;
  }
  return a.tieId.localeCompare(b.tieId);
}

function normalizedPublicText(value: string): string {
  return value.trim().replace(/\s+/gu, " ");
}

function ensureActivityUpdate(
  event: ActivityPresentationEvent,
): ActivityPresentationEvent {
  if (event.updates.length > 0) return event;
  return {
    ...event,
    updates: [
      {
        sequence: event.sequence,
        phase:
          event.status === "success"
            ? "completed"
            : event.status === "error"
              ? "failed"
              : event.kind === "reasoning"
                ? "streaming"
                : "running",
        message: event.summary,
        timestamp: event.timestamp,
        details: event.details,
      },
    ],
  };
}

/**
 * Builds a single, chronological stream combining user messages, assistant replies,
 * clarification questions, checkpoints, protocol cards, tool activities, and published results.
 */
export function buildUnifiedWorkspaceStream({
  project,
  entries,
  draft,
  contract,
  run,
  events,
  artifacts,
  artifactVersionLinks = new Map<string, string>(),
  checkpoint = null,
  pendingUserMessage = null,
}: UnifiedStreamInput): readonly WorkspaceStreamItem[] {
  const sortables: SortableStreamEntry[] = [];
  const assistantMessageTexts = new Set(
    entries
      .filter((entry) => entry.kind === "assistant_message")
      .map((entry) => normalizedPublicText(entry.publicContent)),
  );
  const assistantThreadTexts = new Set(
    entries
      .filter(
        (entry) =>
          entry.kind === "assistant_message" ||
          entry.kind === "assistant_reasoning",
      )
      .map((entry) => normalizedPublicText(entry.publicContent)),
  );

  const answersByQuestionId = new Map<string, string>();
  for (const entry of entries) {
    if (
      entry.kind === "clarification_answer" &&
      entry.structuredPayload.answerToQuestionId
    ) {
      answersByQuestionId.set(
        entry.structuredPayload.answerToQuestionId,
        entry.publicContent,
      );
    }
  }

  let draftRendered = false;

  for (const entry of entries) {
    if (
      entry.kind === "user_message" ||
      entry.kind === "clarification_answer"
    ) {
      const item: UserMessageStreamItem = {
        id: entry.id,
        kind: "user_message",
        message: entry.publicContent,
        timestamp: entry.createdAt,
      };
      sortables.push({
        item,
        timestamp: entry.createdAt,
        sourceRank: 1,
        sequence: entry.sequence,
        tieId: entry.id,
      });
      continue;
    }

    if (entry.kind === "assistant_reasoning") {
      if (
        assistantMessageTexts.has(normalizedPublicText(entry.publicContent))
      ) {
        continue;
      }
      const item: AssistantReasoningStreamItem = {
        id: entry.id,
        kind: "assistant_reasoning",
        content: entry.publicContent,
        isStreaming: false,
        timestamp: entry.createdAt,
      };
      sortables.push({
        item,
        timestamp: entry.createdAt,
        sourceRank: 2,
        sequence: entry.sequence,
        tieId: entry.id,
      });
      continue;
    }

    if (entry.kind === "assistant_message") {
      const outcome =
        "outcome" in entry.structuredPayload &&
        typeof entry.structuredPayload.outcome === "string"
          ? entry.structuredPayload.outcome
          : null;
      const item: AssistantMessageStreamItem = {
        id: entry.id,
        kind: "assistant_message",
        message: entry.publicContent,
        outcome,
        timestamp: entry.createdAt,
      };
      sortables.push({
        item,
        timestamp: entry.createdAt,
        sourceRank: 2,
        sequence: entry.sequence,
        tieId: entry.id,
      });

      const hasDraft =
        "draftId" in entry.structuredPayload &&
        Boolean(entry.structuredPayload.draftId);
      if (hasDraft && (draft || contract)) {
        const protocolItem: ProtocolDraftStreamItem = {
          id: `protocol-card:${entry.id}`,
          kind: "protocol_draft",
          draft,
          contract,
          isConfirmed: contract !== null,
          runStatusLabel: run ? run.status : null,
          timestamp: entry.createdAt,
        };
        sortables.push({
          item: protocolItem,
          timestamp: entry.createdAt,
          sourceRank: 3,
          sequence: entry.sequence,
          tieId: `protocol-card:${entry.id}`,
        });
        draftRendered = true;
      }
      continue;
    }

    if (entry.kind === "clarification_question") {
      const questionId =
        "questionId" in entry.structuredPayload &&
        typeof entry.structuredPayload.questionId === "string"
          ? entry.structuredPayload.questionId
          : entry.id;
      const options =
        "options" in entry.structuredPayload &&
        Array.isArray(entry.structuredPayload.options)
          ? (entry.structuredPayload.options as readonly string[])
          : [];
      const answered = answersByQuestionId.has(questionId);
      const selectedOption = answersByQuestionId.get(questionId) ?? null;

      const item: ClarificationQuestionStreamItem = {
        id: entry.id,
        kind: "clarification_question",
        questionId,
        question: entry.publicContent,
        options,
        answered,
        selectedOption,
        timestamp: entry.createdAt,
      };
      sortables.push({
        item,
        timestamp: entry.createdAt,
        sourceRank: 2,
        sequence: entry.sequence,
        tieId: entry.id,
      });
    }
  }

  // Fallback: If draft/contract exists but wasn't attached to an assistant message yet
  if (!draftRendered && (draft !== null || contract !== null)) {
    const draftTimestamp =
      contract?.createdAt ?? draft?.createdAt ?? project.createdAt;
    const protocolItem: ProtocolDraftStreamItem = {
      id: `protocol-card:${draft?.id ?? contract?.id ?? "active"}`,
      kind: "protocol_draft",
      draft,
      contract,
      isConfirmed: contract !== null,
      runStatusLabel: run ? run.status : null,
      timestamp: draftTimestamp,
    };
    sortables.push({
      item: protocolItem,
      timestamp: draftTimestamp,
      sourceRank: 3,
      sequence: 999999,
      tieId: `protocol-card:${draft?.id ?? contract?.id ?? "active"}`,
    });
  }

  // Checkpoint prompt if active
  if (checkpoint !== null) {
    const item: CheckpointPromptStreamItem = {
      id: `checkpoint:${checkpoint.id}`,
      kind: "checkpoint_prompt",
      checkpointId: checkpoint.id,
      runId: checkpoint.runId,
      runRevision: checkpoint.runRevision,
      question: checkpoint.question,
      options: checkpoint.options,
      checkpointKind: checkpoint.kind,
      repairContext: checkpoint.repairContext,
      answered: checkpoint.isAnswered,
      selectedOption: checkpoint.selectedOption,
      freeText: checkpoint.freeText,
      repairDecisions: checkpoint.repairDecisions,
      repairOutcome: checkpoint.repairOutcome,
      timestamp: checkpoint.createdAt,
    };
    sortables.push({
      item,
      timestamp: checkpoint.createdAt,
      sourceRank: 2,
      sequence: 999999,
      tieId: `checkpoint:${checkpoint.id}`,
    });
  }

  // Activity events from RunEvents
  const mergedEvents = mergeActivityPresentationEvents(
    [],
    events.map(ensureActivityUpdate),
  );
  if (run !== null && mergedEvents.length > 0) {
    for (const event of mergedEvents) {
      if (assistantThreadTexts.has(normalizedPublicText(event.summary))) {
        continue;
      }
      if (event.kind !== "status" && event.kind !== "completion") {
        const item: ToolExecutionStreamItem = {
          id: event.id,
          kind: "tool_execution",
          event,
          timestamp: event.timestamp,
        };
        sortables.push({
          item,
          timestamp: event.timestamp,
          sourceRank: 4,
          sequence: event.sequence,
          tieId: event.id,
        });
      }
    }
  }

  // Published Artifacts enter thread upon publication fact
  const renderedArtifactVersionIds = new Set<string>();
  if (run !== null && mergedEvents.length > 0) {
    for (const event of mergedEvents) {
      if (event.artifactVersionIds && event.artifactVersionIds.length > 0) {
        for (const versionId of event.artifactVersionIds) {
          if (!renderedArtifactVersionIds.has(versionId)) {
            const linkedArtifactId = artifactVersionLinks.get(versionId);
            const artifact = artifacts.find(
              (a) =>
                a.id === linkedArtifactId || a.latestVersionId === versionId,
            );
            if (artifact) {
              const item: ArtifactResultStreamItem = {
                id: `artifact-result:${versionId}`,
                kind: "artifact_result",
                artifact,
                versionId,
                title: artifact.title,
                summary: null,
                timestamp: event.timestamp,
              };
              sortables.push({
                item,
                timestamp: event.timestamp,
                sourceRank: 5,
                sequence: event.sequence,
                tieId: `artifact-result:${versionId}`,
              });
              renderedArtifactVersionIds.add(versionId);
            }
          }
        }
      }
    }
  }

  // A Thread result block anchors only on the real publication event; there is
  // deliberately no artifact.createdAt fallback placement.

  // Sort all persisted items deterministically
  sortables.sort(compareSortableEntries);
  const items: WorkspaceStreamItem[] = sortables.map((s) => s.item);

  // Append transient pending user message at the client tail only
  if (pendingUserMessage) {
    items.push({
      id: "pending:user-message",
      kind: "user_message",
      message: pendingUserMessage,
      timestamp: "",
    });
  }

  return Object.freeze(items);
}
