import type { AgentWorkspaceRuntime } from "../../../root";

interface ConversationNameWithStatusProps {
  readonly runtime: AgentWorkspaceRuntime;
}

/** OpenHands conversation title seam, reduced to the current desktop workspace status. */
export function ConversationNameWithStatus({
  runtime,
}: ConversationNameWithStatusProps) {
  return (
    <div className="flex min-w-0 items-center gap-2">
      <h1 id="agent-task-heading" className="shrink-0 text-sm font-semibold">
        研究工作台
      </h1>
      <p className="truncate text-xs text-[var(--oh-muted)]">
        {runtime.availability === "ready" ? "运行服务已连接" : "运行服务未连接"}
      </p>
    </div>
  );
}
