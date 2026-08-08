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
  const [commands, setCommands] = React.useState<string[]>([]);
  const [phase, setPhase] = React.useState<ExecutionPhase>("idle");
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [lastCommand, setLastCommand] = React.useState<string | null>(null);
  const abortRef = React.useRef<AbortController | null>(null);
  const scrollAnchorRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    scrollAnchorRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [commands, phase]);

  React.useEffect(
    () => () => {
      abortRef.current?.abort();
    },
    [],
  );

  const execute = React.useCallback(
    async (command: string, recordCommand: boolean) => {
      if (runtime.availability !== "ready") return;

      const controller = new AbortController();
      abortRef.current?.abort();
      abortRef.current = controller;
      setLastCommand(command);
      if (recordCommand) setCommands((current) => [...current, command]);
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
        {commands.length === 0 && phase !== "running" ? (
          <div className="flex min-h-full items-center justify-center px-8 py-10 text-center">
            <div className="max-w-sm">
              <MessageSquareText
                className="mx-auto size-7 text-[var(--oh-text-dim)]"
                aria-hidden="true"
              />
              <h2 className="mt-4 font-serif text-xl font-medium text-[var(--oh-text)]">
                从一条明确指令开始
              </h2>
              <p className="mt-2 text-sm leading-6 text-[var(--oh-muted)]">
                连接 Agent 运行服务后，可在下方描述任务。
              </p>
            </div>
          </div>
        ) : (
          <ol className="space-y-4 px-5 py-5" aria-label="已提交指令">
            {commands.map((command, index) => (
              <li
                key={`${index}-${command}`}
                className="ml-auto max-w-[86%] border-r-2 border-[var(--oh-accent)] pr-3 text-right"
              >
                <p className="whitespace-pre-wrap text-sm leading-6 text-[var(--oh-text)]">
                  {command}
                </p>
                <span className="text-xs text-[var(--oh-text-dim)]">
                  用户指令
                </span>
              </li>
            ))}
          </ol>
        )}

        {phase === "running" ? <ChatMessagesSkeleton /> : null}
        {error ? (
          <ErrorMessageBanner
            message={error}
            onRetry={() => {
              if (lastCommand) void execute(lastCommand, false);
            }}
            onDismiss={() => {
              setError(null);
              setPhase("idle");
            }}
            isRetrying={phase === "running"}
          />
        ) : null}
        {notice ? (
          <p className="px-5 py-3 text-sm text-[var(--oh-muted)]" role="status">
            {notice}
          </p>
        ) : null}
        <div ref={scrollAnchorRef} aria-hidden="true" />
      </div>

      <InteractiveChatBox
        disabled={runtime.availability !== "ready"}
        running={phase === "running"}
        onSubmit={(command) => void execute(command, true)}
        onCancel={cancel}
      />
    </div>
  );
}
