import React from "react";
import { Button } from "@xingwen/ui";
import { FileSearch } from "@xingwen/ui/icons";

import type { ResearchWorkspaceRuntime } from "../../../root";

import { ErrorMessageBanner } from "./error-message-banner";
import { InteractiveChatBox } from "./interactive-chat-box";

interface ChatInterfaceProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

export function ChatInterface({ runtime }: ChatInterfaceProps) {
  const [lastIntent, setLastIntent] = React.useState<string | null>(null);
  const [lastAttemptedIntent, setLastAttemptedIntent] = React.useState<
    string | null
  >(null);
  const [error, setError] = React.useState<string | null>(null);

  const submitIntent = React.useCallback(
    async (intent: string) => {
      const submit = runtime.composer.submitIntent;
      if (!submit) return;
      setError(null);
      setLastAttemptedIntent(intent);
      try {
        await submit(intent);
        setLastIntent(intent);
      } catch (reason) {
        setError(
          reason instanceof Error
            ? reason.message
            : "研究意图提交失败，请重试。",
        );
        throw reason;
      }
    },
    [runtime],
  );

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[var(--oh-canvas)]">
      <div
        className="min-h-0 flex-1 overflow-y-auto"
        aria-live="polite"
        aria-busy={runtime.composer.submitting}
      >
        {runtime.activation ? (
          <div className="flex min-h-full items-center justify-center px-[var(--oh-space-8)] py-[var(--oh-space-8)] text-center">
            <section
              className="max-w-md"
              aria-labelledby="workspace-activation-title"
            >
              <FileSearch
                className="mx-auto size-7 text-[var(--oh-text-dim)]"
                aria-hidden="true"
              />
              <h2
                id="workspace-activation-title"
                className="oh-font-serif mt-[var(--oh-space-4)] text-[length:var(--oh-font-size-heading)] leading-[var(--oh-line-height-heading)] font-medium text-[var(--oh-text)]"
              >
                {runtime.activation.title}
              </h2>
              <p className="mx-auto mt-[var(--oh-space-2)] max-w-[60ch] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-muted)]">
                {runtime.activation.description}
              </p>
              <Button
                className="mt-[var(--oh-space-5)]"
                onClick={runtime.activation.onAction}
              >
                {runtime.activation.actionLabel}
              </Button>
            </section>
          </div>
        ) : lastIntent ? (
          <div className="mx-auto flex min-h-full w-full max-w-[var(--oh-content-max-inline-size)] flex-col justify-end gap-[var(--oh-space-4)] px-[var(--oh-space-6)] py-[var(--oh-space-8)]">
            <section
              className="research-intent-message"
              aria-label="已提交的研究意图"
            >
              <p className="research-intent-message__label">研究意图</p>
              <p>{lastIntent}</p>
            </section>
            <p className="text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-muted)]">
              请在右侧“上下文”面板完成研究协议检查点。
            </p>
          </div>
        ) : (
          <div className="flex min-h-full items-center justify-center px-[var(--oh-space-8)] py-[var(--oh-space-8)] text-center">
            <div className="max-w-md">
              <FileSearch
                className="mx-auto size-7 text-[var(--oh-text-dim)]"
                aria-hidden="true"
              />
              <h2 className="oh-font-serif mt-[var(--oh-space-4)] text-[length:var(--oh-font-size-heading)] leading-[var(--oh-line-height-heading)] font-medium text-[var(--oh-text)]">
                先写下研究意图
              </h2>
              <p className="mt-[var(--oh-space-2)] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-muted)]">
                描述希望回答的问题。系统会打开结构化研究协议，由你补齐范围、来源、证据与质量约束。
              </p>
            </div>
          </div>
        )}
        {error ? (
          <ErrorMessageBanner
            message={error}
            onRetry={() => {
              if (lastAttemptedIntent) void submitIntent(lastAttemptedIntent);
            }}
            onDismiss={() => setError(null)}
            isRetrying={runtime.composer.submitting}
          />
        ) : null}
      </div>

      {runtime.composer.submitIntent ? (
        <InteractiveChatBox
          disabled={!runtime.composer.canSubmitIntent}
          submitting={runtime.composer.submitting}
          onSubmit={submitIntent}
        />
      ) : null}
    </div>
  );
}
