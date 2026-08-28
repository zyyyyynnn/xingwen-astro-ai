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
      className="flex size-[var(--control-size-xs)] items-center justify-center rounded-[var(--radius-pill)] border border-[var(--color-brand)] bg-[var(--color-brand)] text-[var(--color-brand-on)] hover:bg-[var(--color-brand-hover)] disabled:border-[var(--color-border)] disabled:bg-[var(--color-surface-muted)] disabled:text-[var(--color-ink-tertiary)]"
      data-testid="submit-button"
      aria-label={submitting ? "正在发送研究消息" : "发送研究消息"}
      onClick={handleSubmit}
      disabled={disabled}
    >
      <ArrowUp className="size-[var(--icon-size-sm)]" aria-hidden="true" />
    </button>
  );
}
