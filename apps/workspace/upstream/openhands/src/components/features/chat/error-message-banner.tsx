import { RotateCcw, X } from "lucide-react";

interface ErrorMessageBannerProps {
  readonly message: string;
  readonly onRetry: () => void;
  readonly onDismiss: () => void;
  readonly isRetrying?: boolean;
}

export function ErrorMessageBanner({
  message,
  onRetry,
  onDismiss,
  isRetrying = false,
}: ErrorMessageBannerProps) {
  return (
    <section
      className="mx-5 my-3 border-l-2 border-[var(--oh-error)] bg-[var(--oh-error-muted)] p-3 text-sm"
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-[var(--oh-text)]">任务执行失败</p>
          <details className="mt-1 text-[var(--oh-muted)]">
            <summary className="cursor-pointer">错误详情</summary>
            <p className="mt-1 break-words">{message}</p>
          </details>
        </div>
        <button
          type="button"
          className="oh-icon-button"
          aria-label="关闭错误提示"
          onClick={onDismiss}
        >
          <X className="size-4" aria-hidden="true" />
        </button>
      </div>
      <button
        type="button"
        className="mt-3 inline-flex items-center gap-2 rounded-[var(--oh-radius-sm)] border border-[var(--oh-border-strong)] px-3 py-1.5 font-medium text-[var(--oh-text)] hover:bg-[var(--oh-surface-raised)]"
        onClick={onRetry}
        disabled={isRetrying}
      >
        <RotateCcw className="size-4" aria-hidden="true" />
        {isRetrying ? "正在重试" : "重试"}
      </button>
    </section>
  );
}
