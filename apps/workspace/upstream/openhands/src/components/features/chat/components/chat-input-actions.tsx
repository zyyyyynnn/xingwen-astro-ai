import { ChatSendButton } from "../chat-send-button";

interface ChatInputActionsProps {
  readonly disabled: boolean;
  readonly canSubmit: boolean;
  readonly submitting: boolean;
  readonly handleSubmit: () => void;
}

export function ChatInputActions({
  disabled,
  canSubmit,
  submitting,
  handleSubmit,
}: ChatInputActionsProps) {
  return (
    <div
      data-testid="chat-input-actions"
      className="flex min-h-[var(--oh-control-size-xs)] w-full items-center justify-between gap-[var(--oh-space-3)]"
    >
      <p className="text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
        Enter 提交 · Shift+Enter 换行
      </p>
      <ChatSendButton
        handleSubmit={handleSubmit}
        disabled={disabled || !canSubmit || submitting}
        submitting={submitting}
      />
    </div>
  );
}
