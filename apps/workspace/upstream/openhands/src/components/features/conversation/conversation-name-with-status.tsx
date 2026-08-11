import { Badge } from "@xingwen/ui";

import type { ResearchWorkspaceRuntime } from "../../../root";

interface ConversationNameWithStatusProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

export function ConversationNameWithStatus({
  runtime,
}: ConversationNameWithStatusProps) {
  return (
    <div className="flex min-w-0 items-center gap-[var(--oh-space-3)]">
      <h1
        id="research-project-heading"
        className="truncate text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] font-semibold"
      >
        {runtime.project?.name ?? "新研究"}
      </h1>
      {runtime.run ? (
        <>
          <Badge variant="secondary">{runtime.run.status}</Badge>
          <p className="truncate text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-muted)]">
            {runtime.run.executionMode}
          </p>
        </>
      ) : runtime.project ? (
        <p className="truncate text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-muted)]">
          等待研究协议
        </p>
      ) : (
        <p className="truncate text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-muted)]">
          创建项目后开始
        </p>
      )}
    </div>
  );
}
