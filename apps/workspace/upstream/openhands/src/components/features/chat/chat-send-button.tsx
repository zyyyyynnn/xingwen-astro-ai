import { ArrowUp } from "@xingwen/ui/icons";

interface ChatSendButtonProps {
  readonly handleSubmit: () => void;
  readonly disabled: boolean;
  readonly submitting: boolean;
}

export function ChatSendButton({
  handleSubmit,
  disabled,
  submitting,
}: ChatSendButtonProps) {
  return (
    <button
      type="button"
      className="flex size-[var(--oh-control-size-xs)] items-center justify-center rounded-[var(--oh-radius-pill)] border border-[var(--oh-accent)] bg-[var(--oh-accent)] text-[var(--oh-accent-on)] hover:bg-[var(--oh-accent-hover)] disabled:border-[var(--oh-border)] disabled:bg-[var(--oh-surface-muted)] disabled:text-[var(--oh-text-dim)]"
      data-testid="submit-button"
      aria-label={submitting ? "正在提交研究意图" : "提交研究意图"}
      onClick={handleSubmit}
      disabled={disabled}
    >
      <ArrowUp className="size-[var(--oh-icon-size-sm)]" aria-hidden="true" />
    </button>
  );
}
