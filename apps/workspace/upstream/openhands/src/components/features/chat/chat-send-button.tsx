import { ArrowUp } from "lucide-react";

interface ChatSendButtonProps {
  readonly handleSubmit: () => void;
  readonly disabled: boolean;
}

export function ChatSendButton({
  handleSubmit,
  disabled,
}: ChatSendButtonProps) {
  return (
    <button
      type="button"
      className="flex size-8 items-center justify-center rounded-[var(--oh-radius-pill)] border border-[var(--oh-accent)] bg-[var(--oh-accent)] text-[var(--oh-accent-on)] hover:bg-[var(--oh-accent-hover)] disabled:border-[var(--oh-border)] disabled:bg-[var(--oh-surface-muted)] disabled:text-[var(--oh-text-dim)]"
      data-testid="submit-button"
      aria-label="发送指令"
      onClick={handleSubmit}
      disabled={disabled}
    >
      <ArrowUp className="size-4" aria-hidden="true" />
    </button>
  );
}
