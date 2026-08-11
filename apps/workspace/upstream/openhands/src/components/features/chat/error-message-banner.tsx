import { buttonClassName } from "@xingwen/ui";
import { RotateCcw, X } from "@xingwen/ui/icons";

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
      className="mx-[var(--oh-space-6)] my-[var(--oh-space-3)] border border-[var(--oh-error)] bg-[var(--oh-error-muted)] p-[var(--oh-space-3)] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]"
      role="alert"
    >
      <div className="flex items-start gap-[var(--oh-space-3)]">
        <div className="min-w-0 flex-1">
          <p className="font-semibold text-[var(--oh-text)]">
            研究意图提交失败
          </p>
          <details className="mt-[var(--oh-space-1)] text-[var(--oh-muted)]">
            <summary className="cursor-pointer">查看安全错误说明</summary>
            <p className="mt-[var(--oh-space-1)] break-words">{message}</p>
          </details>
        </div>
        <button
          type="button"
          className={buttonClassName({ variant: "ghost", size: "icon" })}
          aria-label="关闭错误提示"
          onClick={onDismiss}
        >
          <X className="size-[var(--oh-icon-size-md)]" aria-hidden="true" />
        </button>
      </div>
      <button
        type="button"
        className="mt-[var(--oh-space-3)] inline-flex items-center gap-[var(--oh-space-2)] rounded-[var(--oh-radius-sm)] border border-[var(--oh-border-strong)] px-[var(--oh-space-3)] py-[var(--oh-space-2)] font-medium text-[var(--oh-text)] hover:bg-[var(--oh-surface-raised)]"
        onClick={onRetry}
        disabled={isRetrying}
      >
        <RotateCcw
          className="size-[var(--oh-icon-size-md)]"
          aria-hidden="true"
        />
        {isRetrying ? "正在重试" : "重试"}
      </button>
    </section>
  );
}
