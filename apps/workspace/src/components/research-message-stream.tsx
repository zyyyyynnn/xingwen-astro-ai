import { memo, useMemo, type ReactNode } from "react";
import type {
  DomainEntityId,
  RunCheckpointDecisionRequest,
} from "@xingwen/domain";
import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  WorkspaceStreamItem,
} from "@xingwen/research-adapter";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";

import { ChatMessage, CollapsibleThinking, Messages } from "../mechanics/root";
import { ClarificationPrompt } from "./clarification-prompt";
import { ChoicePrompt } from "./choice-prompt";
import { ScientificRepairPrompt } from "./scientific-repair-prompt";
import { resolveArtifactRenderer } from "../presentation/artifact-renderer-registry";

interface ResearchMessageStreamProps {
  readonly runtime?: WorkspaceRuntimeBoundaries;
  readonly projectId?: DomainEntityId;
  readonly items: readonly WorkspaceStreamItem[];
  readonly onOpenArtifactVersion?: (artifactVersionId: DomainEntityId) => void;
  readonly onConfirmProtocol?: () => Promise<void> | void;
  readonly onOpenProtocolEditor?: () => void;
  readonly onRefineInChat?: () => void;
  readonly onViewPlan?: () => void;
  readonly isConfirmingProtocol?: boolean;
  readonly onAnswerQuestion?: (
    questionId: string,
    suggestedAnswer?: string,
  ) => void;
  readonly onCheckpointDecision?: (
    runId: string,
    decision: RunCheckpointDecisionRequest,
  ) => void;
  readonly isSubmittingCheckpoint?: boolean;
  readonly renderProtocolDraft?: (props: {
    readonly draft: ResearchContractDraftViewModel | null;
    readonly contract: ResearchContractViewModel | null;
    readonly isConfirmed: boolean;
    readonly runStatusLabel: string | null;
    readonly onConfirm?: () => Promise<void> | void;
    readonly onOpenEditor?: () => void;
    readonly onRefineInChat?: () => void;
    readonly onViewPlan?: () => void;
    readonly isConfirming?: boolean;
  }) => ReactNode;
  readonly renderStepProgress?: (props: {
    readonly currentStep: number;
    readonly totalSteps: number;
    readonly stepLabel: string;
    readonly artifactsCount: number;
    readonly status: "running" | "completed" | "error";
  }) => ReactNode;
}

type StreamRenderBlock =
  | { readonly kind: "item"; readonly item: WorkspaceStreamItem }
  | {
      readonly kind: "tool_events";
      readonly id: string;
      readonly events: readonly Extract<
        WorkspaceStreamItem,
        { readonly kind: "tool_execution" }
      >["event"][];
    };

function groupToolEvents(
  items: readonly WorkspaceStreamItem[],
): readonly StreamRenderBlock[] {
  const blocks: StreamRenderBlock[] = [];
  let events: Extract<
    WorkspaceStreamItem,
    { readonly kind: "tool_execution" }
  >["event"][] = [];

  const flush = () => {
    if (events.length === 0) return;
    blocks.push({
      kind: "tool_events",
      id: `tool-stream:${events[0]?.id ?? blocks.length}`,
      events,
    });
    events = [];
  };

  for (const item of items) {
    if (item.kind === "tool_execution" && item.event.kind !== "reasoning") {
      events.push(item.event);
    } else {
      flush();
      blocks.push({ kind: "item", item });
    }
  }
  flush();
  return blocks;
}

/** Product seam between research view models and current Workspace mechanics. */
export const ResearchMessageStream = memo(function ResearchMessageStream({
  runtime,
  projectId,
  items,
  onOpenArtifactVersion,
  onConfirmProtocol,
  onOpenProtocolEditor,
  onRefineInChat,
  onViewPlan,
  isConfirmingProtocol = false,
  onAnswerQuestion,
  onCheckpointDecision,
  isSubmittingCheckpoint = false,
  renderProtocolDraft,
  renderStepProgress,
}: ResearchMessageStreamProps) {
  const blocks = useMemo(() => groupToolEvents(items), [items]);

  return (
    <div
      className="agent-message-stream flex flex-col gap-2"
      data-testid="agent-message-stream"
      role="region"
      aria-label="Agent 消息流"
    >
      {blocks.map((block) => {
        if (block.kind === "tool_events") {
          return (
            <Messages
              key={block.id}
              events={block.events}
              onOpenArtifactVersion={onOpenArtifactVersion}
            />
          );
        }

        const { item } = block;
        if (item.kind === "user_message") {
          return (
            <ChatMessage
              key={item.id}
              type="user"
              message={item.message}
              pendingStatus={
                item.id === "pending:user-message" ? "sending" : undefined
              }
            />
          );
        }

        if (item.kind === "tool_execution" && item.event.kind === "reasoning") {
          return (
            <CollapsibleThinking
              key={item.id}
              content={item.event.summary}
              isStreaming={
                item.event.status === "pending" ||
                item.event.status === "running"
              }
              label="分析"
            />
          );
        }

        if (item.kind === "assistant_reasoning") {
          return (
            <CollapsibleThinking
              key={item.id}
              content={item.content}
              isStreaming={item.isStreaming}
              label="分析"
            />
          );
        }

        if (item.kind === "assistant_message") {
          return (
            <ChatMessage key={item.id} type="agent" message={item.message} />
          );
        }

        if (item.kind === "clarification_question") {
          return (
            <ChatMessage key={item.id} type="agent" message="">
              <ClarificationPrompt
                id={item.id}
                questionId={item.questionId}
                question={item.question}
                options={item.options}
                answered={item.answered}
                selectedOption={item.selectedOption}
                onAnswer={(qId, ans) => onAnswerQuestion?.(qId, ans)}
              />
            </ChatMessage>
          );
        }

        if (item.kind === "checkpoint_prompt") {
          return (
            <ChatMessage key={item.id} type="agent" message="">
              {item.checkpointKind === "scientific_repair" &&
              item.repairContext ? (
                <ScientificRepairPrompt
                  id={item.id}
                  question={item.question}
                  context={item.repairContext}
                  decisions={item.repairDecisions}
                  outcome={item.repairOutcome}
                  answered={item.answered}
                  isSubmitting={isSubmittingCheckpoint}
                  onSubmit={(repairDecisions) =>
                    onCheckpointDecision?.(item.runId, {
                      checkpointId: item.checkpointId as DomainEntityId,
                      expectedRunRevision: item.runRevision,
                      repairDecisions,
                    })
                  }
                />
              ) : (
                <ChoicePrompt
                  id={item.id}
                  question={item.question}
                  options={item.options}
                  answered={item.answered}
                  selectedOption={item.selectedOption}
                  freeText={item.freeText}
                  allowFreeText={true}
                  isSubmitting={isSubmittingCheckpoint}
                  onSelect={(selectedOption, freeText) =>
                    onCheckpointDecision?.(item.runId, {
                      checkpointId: item.checkpointId as DomainEntityId,
                      expectedRunRevision: item.runRevision,
                      selectedOption,
                      freeText,
                    })
                  }
                />
              )}
            </ChatMessage>
          );
        }

        if (item.kind === "protocol_draft") {
          return renderProtocolDraft ? (
            <div key={item.id}>
              {renderProtocolDraft({
                draft: item.draft,
                contract: item.contract,
                isConfirmed: item.isConfirmed,
                runStatusLabel: item.runStatusLabel,
                onConfirm: onConfirmProtocol,
                onOpenEditor: onOpenProtocolEditor,
                onRefineInChat,
                onViewPlan,
                isConfirming: isConfirmingProtocol,
              })}
            </div>
          ) : null;
        }

        if (item.kind === "step_progress") {
          return renderStepProgress ? (
            <div key={item.id}>
              {renderStepProgress({
                currentStep: item.currentStep,
                totalSteps: item.totalSteps,
                stepLabel: item.stepLabel,
                artifactsCount: item.artifactsCount,
                status: item.status,
              })}
            </div>
          ) : null;
        }

        if (item.kind === "artifact_result") {
          const descriptor = resolveArtifactRenderer(item.artifact.kind);
          if (!descriptor) {
            return (
              <div
                key={item.id}
                className="my-2 rounded-lg border border-border/70 p-4 text-sm"
              >
                当前结果类型暂时无法显示。
              </div>
            );
          }
          const ThreadRenderer = descriptor.ThreadRenderer;
          return (
            <ThreadRenderer
              key={item.id}
              runtime={runtime}
              projectId={projectId}
              artifact={item.artifact}
              versionId={item.versionId}
              summary={item.summary}
              onOpen={
                onOpenArtifactVersion
                  ? () => onOpenArtifactVersion(item.versionId)
                  : null
              }
            />
          );
        }

        return null;
      })}
    </div>
  );
});

ResearchMessageStream.displayName = "ResearchMessageStream";
