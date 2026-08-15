import type { ResearchThreadEntryViewModel } from "@xingwen/research-adapter";
import { Alert, AlertDescription, Button } from "@xingwen/ui";
import { CheckCircle2, ChevronRight } from "@xingwen/ui/icons";
import type { ReactNode } from "react";

import {
  ChatMessage,
  CollapsibleRationale,
} from "../../upstream/openhands/src/root";

export interface ResearchThreadProjection {
  readonly id: string;
  readonly occurredAt: string;
  readonly node: ReactNode;
}

interface ResearchThreadProps {
  readonly entries: readonly ResearchThreadEntryViewModel[];
  readonly loading: boolean;
  readonly loadError: string | null;
  readonly submitting: boolean;
  readonly pendingMessage: string | null;
  readonly projections: readonly ResearchThreadProjection[];
  readonly onAnswer: (questionId: string, suggestedAnswer?: string) => void;
  readonly onOpenDraft: (draftId: string) => void;
  readonly onRetryLoad: () => void;
}

const OUTCOME_LABELS: Readonly<Record<string, string>> = {
  clarification_required: "需要澄清",
  draft_ready: "协议草案已生成",
  partial: "部分完成",
  unsupported: "暂不支持",
  refused: "无法处理",
};

function ProtocolDraftCheckpoint({ onOpen }: { readonly onOpen: () => void }) {
  return (
    <div className="oh-narrative-node oh-narrative-row">
      <span className="oh-narrative-disclosure-slot" aria-hidden="true" />
      <CheckCircle2 className="oh-narrative-icon" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium leading-5 text-[var(--oh-text)]">
          研究协议草案已生成
        </p>
        <p className="text-xs leading-5 text-[var(--oh-muted)]">
          检查研究边界、字段、来源与交付要求
        </p>
      </div>
      <Button
        variant="ghost"
        size="small"
        className="shrink-0 self-center"
        onClick={onOpen}
      >
        查看协议
        <ChevronRight aria-hidden="true" />
      </Button>
    </div>
  );
}

function ThreadEntry({
  entry,
  answered,
  onAnswer,
  onOpenDraft,
}: {
  readonly entry: ResearchThreadEntryViewModel;
  readonly answered: boolean;
  readonly onAnswer: (questionId: string, suggestedAnswer?: string) => void;
  readonly onOpenDraft: (draftId: string) => void;
}) {
  if (entry.kind === "assistant_analysis") {
    return (
      <CollapsibleRationale summary="分析">
        <p>{entry.publicContent}</p>
      </CollapsibleRationale>
    );
  }
  const question = entry.kind === "clarification_question";
  const outcome =
    entry.kind === "user_message" || entry.kind === "clarification_answer"
      ? null
      : entry.structuredPayload.outcome;
  const draftId =
    entry.kind === "user_message" || entry.kind === "clarification_answer"
      ? null
      : entry.structuredPayload.draftId;
  const questionId = question ? entry.structuredPayload.questionId : null;
  const options = question ? entry.structuredPayload.options : [];
  return (
    <ChatMessage
      type={entry.actor === "user" ? "user" : "agent"}
      message={entry.publicContent}
      interactive={question}
    >
      {outcome !== null && draftId === null ? (
        <span className="text-xs text-[var(--oh-muted)]">
          {OUTCOME_LABELS[outcome] ?? "研究状态已更新"}
        </span>
      ) : null}
      {draftId !== null && entry.kind === "assistant_message" ? (
        <ProtocolDraftCheckpoint onOpen={() => onOpenDraft(draftId)} />
      ) : null}
      {entry.kind === "clarification_question" && questionId !== null ? (
        answered ? (
          <span className="inline-flex items-center gap-1 text-xs text-[var(--oh-status-success)]">
            <CheckCircle2 aria-hidden="true" /> 已回答
          </span>
        ) : (
          <div className="flex flex-wrap gap-2">
            {options.map((option) => (
              <Button
                key={option}
                variant="secondary"
                size="small"
                onClick={() => onAnswer(questionId, option)}
              >
                {option}
              </Button>
            ))}
            <Button
              variant={options.length > 0 ? "ghost" : "secondary"}
              size="small"
              onClick={() => onAnswer(questionId)}
            >
              {options.length > 0 ? "填写其他回答" : "回答这个问题"}
            </Button>
          </div>
        )
      ) : null}
    </ChatMessage>
  );
}

export function ResearchThread({
  entries,
  loading,
  loadError,
  submitting,
  pendingMessage,
  projections,
  onAnswer,
  onOpenDraft,
  onRetryLoad,
}: ResearchThreadProps) {
  const hasConversationContent =
    entries.length > 0 || projections.length > 0 || pendingMessage !== null;
  const answeredQuestionIds = new Set(
    entries
      .filter((entry) => entry.kind === "clarification_answer")
      .map((entry) => entry.structuredPayload.answerToQuestionId)
      .filter((value) => value !== null),
  );
  const projectionsByIndex = groupThreadProjections(entries, projections);

  return (
    <section
      className={`mx-auto flex w-full max-w-[var(--oh-content-max-inline-size)] flex-col px-[var(--oh-space-2)] ${hasConversationContent ? "min-h-full flex-1 justify-start" : "flex-none"}`}
      aria-label="研究对话"
    >
      <div
        className="flex min-h-0 w-full flex-col"
        aria-live="polite"
        aria-busy={loading || submitting}
      >
        {loading ? (
          <p className="text-sm text-[var(--oh-muted)]">正在恢复研究对话…</p>
        ) : null}
        {!loading && loadError ? (
          <div className="mx-auto w-full max-w-md">
            <Alert variant="destructive">
              <AlertDescription>{loadError}</AlertDescription>
            </Alert>
            <Button
              variant="ghost"
              size="small"
              className="mt-2"
              onClick={onRetryLoad}
            >
              重新载入研究对话
            </Button>
          </div>
        ) : null}
        {!loading && !loadError && !hasConversationContent ? (
          <div className="mx-auto mb-[var(--oh-space-6)] max-w-md text-center">
            <h1 className="oh-font-serif text-[length:var(--oh-font-size-heading)] font-medium leading-[var(--oh-line-height-heading)] text-[var(--oh-text)]">
              开始你的研究
            </h1>
            <p className="mt-[var(--oh-space-2)] text-sm leading-6 text-[var(--oh-muted)]">
              描述想研究的问题、对象或预期成果
            </p>
          </div>
        ) : null}
        {entries.map((entry, index) => (
          <div className="contents" key={entry.id}>
            {projectionsByIndex.get(index)?.map((projection) => (
              <div className="contents" key={projection.id}>
                {projection.node}
              </div>
            ))}
            <ThreadEntry
              entry={entry}
              answered={
                entry.kind === "clarification_question" &&
                answeredQuestionIds.has(entry.structuredPayload.questionId)
              }
              onAnswer={onAnswer}
              onOpenDraft={onOpenDraft}
            />
          </div>
        ))}
        {projectionsByIndex.get(entries.length)?.map((projection) => (
          <div className="contents" key={projection.id}>
            {projection.node}
          </div>
        ))}
        {pendingMessage ? (
          <ChatMessage
            type="user"
            message={pendingMessage}
            pendingStatus="sending"
          />
        ) : null}
        {submitting ? (
          <p className="my-2 py-1 text-sm text-[var(--oh-muted)]" role="status">
            研究助手正在理解问题并整理下一步…
          </p>
        ) : null}
      </div>
    </section>
  );
}

export function threadProjectionInsertionIndex(
  entries: readonly ResearchThreadEntryViewModel[],
  occurredAt: string,
): number {
  const projectionTime = Date.parse(occurredAt);
  if (!Number.isFinite(projectionTime)) return entries.length;
  const index = entries.findIndex((entry) => {
    const entryTime = Date.parse(entry.createdAt);
    return Number.isFinite(entryTime) && entryTime > projectionTime;
  });
  return index < 0 ? entries.length : index;
}

export function groupThreadProjections(
  entries: readonly ResearchThreadEntryViewModel[],
  projections: readonly ResearchThreadProjection[],
): ReadonlyMap<number, readonly ResearchThreadProjection[]> {
  const groups = new Map<number, ResearchThreadProjection[]>();
  const ordered = [...projections].sort((left, right) => {
    const leftTime = Date.parse(left.occurredAt);
    const rightTime = Date.parse(right.occurredAt);
    const timestampOrder =
      (Number.isFinite(leftTime) ? leftTime : Number.POSITIVE_INFINITY) -
      (Number.isFinite(rightTime) ? rightTime : Number.POSITIVE_INFINITY);
    return timestampOrder || left.id.localeCompare(right.id);
  });
  for (const projection of ordered) {
    const index = threadProjectionInsertionIndex(
      entries,
      projection.occurredAt,
    );
    const group = groups.get(index) ?? [];
    group.push(projection);
    groups.set(index, group);
  }
  return groups;
}
