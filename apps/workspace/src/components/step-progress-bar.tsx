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
      className="my-3 flex w-full items-center justify-between rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-hover)] px-3.5 py-2 text-xs text-[var(--color-ink-primary)] shadow-[var(--shadow-float)]"
      data-testid="step-progress-bar"
      role="status"
    >
      <div className="flex items-center gap-2 font-medium">
        {isRunning ? (
          <Loader2 className="size-3.5 animate-spin text-[var(--color-brand)]" />
        ) : isCompleted ? (
          <CheckCircle2 className="size-3.5 text-[var(--color-success)]" />
        ) : isError ? (
          <XCircle className="size-3.5 text-[var(--color-error)]" />
        ) : (
          <RotateCcw className="size-3.5 text-[var(--color-ink-secondary)]" />
        )}
        <span>
          第 {currentStep} / {Math.max(totalSteps, currentStep)} 步
        </span>
        <span className="text-[var(--color-ink-secondary)]">·</span>
        <span className="text-[var(--color-ink-secondary)]">{stepLabel}</span>
      </div>

      <div className="flex items-center gap-2 text-[var(--color-ink-secondary)]">
        {artifactsCount > 0 ? (
          <span className="text-[var(--color-success)] font-medium">
            {artifactsCount} 个产物已就绪
          </span>
        ) : (
          <span>正在生成科研产物…</span>
        )}
      </div>
    </div>
  );
}
