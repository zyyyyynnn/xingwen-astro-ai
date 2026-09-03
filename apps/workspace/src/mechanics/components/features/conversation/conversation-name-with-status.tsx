import type { ResearchWorkspaceRuntime } from "../../../root";

interface ConversationNameWithStatusProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

export function ConversationNameWithStatus({
  runtime,
}: ConversationNameWithStatusProps) {
  return (
    <div className="flex min-w-0 items-center gap-[var(--space-3)]">
      <h1
        id="research-project-heading"
        className="truncate text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)] font-semibold"
      >
        {runtime.project?.name ?? "新研究"}
      </h1>
      {runtime.project ? (
        <p className="truncate text-[length:var(--font-size-ui-label)] leading-[var(--line-height-ui-label)] text-[var(--color-ink-secondary)]">
          {runtime.project.statusLabel}
        </p>
      ) : (
        <p className="truncate text-[length:var(--font-size-ui-label)] leading-[var(--line-height-ui-label)] text-[var(--color-ink-secondary)]">
          创建项目后开始
        </p>
      )}
    </div>
  );
}
