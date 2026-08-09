import React from "react";
import { MessageSquareText } from "lucide-react";

import type { AgentWorkspaceRuntime } from "../../../root";

import { ChatMessagesSkeleton } from "./chat-messages-skeleton";
import { ErrorMessageBanner } from "./error-message-banner";
import { InteractiveChatBox } from "./interactive-chat-box";

interface ChatInterfaceProps {
  readonly runtime: AgentWorkspaceRuntime;
}

type ExecutionPhase = "idle" | "running" | "error";

export function ChatInterface({ runtime }: ChatInterfaceProps) {
  const [phase, setPhase] = React.useState<ExecutionPhase>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [lastCommand, setLastCommand] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);

  React.useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const execute = React.useCallback(
    async (command: string) => {
      if (runtime.availability !== "ready") return;

      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;
      setLastCommand(command);
      setError(null);
      setNotice(null);
      setPhase("running");

      try {
        await runtime.execute(command, controller.signal);
        if (!controller.signal.aborted) {
          setPhase("idle");
          setNotice("任务已结束");
        }
      } catch (reason) {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "Agent 运行失败");
        setPhase("error");
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
      }
    },
    [runtime],
  );

  const cancel = () => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPhase("idle");
    setNotice("任务已取消");
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col bg-[var(--oh-canvas)]">
      <div
        className="min-h-0 flex-1 overflow-y-auto"
        aria-live="polite"
        aria-busy={phase === "running"}
      >
        {phase === "idle" && !notice ? (
          <div className="flex min-h-full items-center justify-center px-[var(--oh-space-8)] py-[var(--oh-space-8)] text-center">
            <div className="max-w-sm">
              <MessageSquareText
                className="mx-auto size-7 text-[var(--oh-text-dim)]"
                aria-hidden="true"
              />
              <h2 className="mt-4 font-serif text-[length:var(--oh-font-size-heading)] font-medium text-[var(--oh-text)]">
                从一条明确指令开始
              </h2>
              <p className="mt-2 text-[length:var(--oh-font-size-body)] leading-6 text-[var(--oh-muted)]">
                连接 Agent 运行服务后，可在下方描述任务。
              </p>
            </div>
          </div>
        ) : null}

        {phase === "running" ? <ChatMessagesSkeleton /> : null}
        {error ? (
          <ErrorMessageBanner
            message={error}
            onRetry={() => {
              if (lastCommand) void execute(lastCommand);
            }}
            onDismiss={() => {
              setError(null);
              setPhase("idle");
            }}
            isRetrying={phase === "running"}
          />
        ) : null}
        {notice ? (
          <p
            className="px-[var(--oh-space-4)] py-[var(--oh-space-3)] text-[length:var(--oh-font-size-body)] text-[var(--oh-muted)]"
            role="status"
          >
            {notice}
          </p>
        ) : null}
      </div>

      <InteractiveChatBox
        disabled={runtime.availability !== "ready"}
        running={phase === "running"}
        onSubmit={(command) => void execute(command)}
        onCancel={cancel}
      />
    </div>
  );
}
