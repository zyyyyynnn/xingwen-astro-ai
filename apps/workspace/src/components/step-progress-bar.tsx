import { CheckCircle2, Loader2, RotateCcw, XCircle } from "@xingwen/ui/icons";

export interface StepProgressBarProps {
  readonly currentStep: number;
  readonly totalSteps: number;
  readonly stepLabel: string;
  readonly artifactsCount: number;
  readonly status: "running" | "completed" | "error";
}

export function StepProgressBar({
  currentStep,
  totalSteps,
  stepLabel,
  artifactsCount,
  status,
}: StepProgressBarProps) {
  const isRunning = status === "running";
  const isCompleted = status === "completed";
  const isError = status === "error";

  return (
    <div
      className="my-3 flex w-full items-center justify-between rounded-[var(--oh-radius-lg)] border border-[var(--oh-border)] bg-[var(--oh-surface-raised)] px-3.5 py-2 text-xs text-[var(--oh-text)] shadow-[var(--oh-shadow-sm)]"
      data-testid="step-progress-bar"
      role="status"
    >
      <div className="flex items-center gap-2 font-medium">
        {isRunning ? (
          <Loader2 className="size-3.5 animate-spin text-[var(--oh-accent)]" />
        ) : isCompleted ? (
          <CheckCircle2 className="size-3.5 text-[var(--oh-status-success)]" />
        ) : isError ? (
          <XCircle className="size-3.5 text-[var(--oh-status-danger)]" />
        ) : (
          <RotateCcw className="size-3.5 text-[var(--oh-muted)]" />
        )}
        <span>
          第 {currentStep} / {Math.max(totalSteps, currentStep)} 步
        </span>
        <span className="text-[var(--oh-muted)]">·</span>
        <span className="text-[var(--oh-muted)]">{stepLabel}</span>
      </div>

      <div className="flex items-center gap-2 text-[var(--oh-muted)]">
        {artifactsCount > 0 ? (
          <span className="text-[var(--oh-status-success)] font-medium">
            {artifactsCount} 个产物已就绪
          </span>
        ) : (
          <span>正在生成科研产物…</span>
        )}
      </div>
    </div>
  );
}
