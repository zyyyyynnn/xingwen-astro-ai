import { ChatSendButton } from "../chat-send-button";
import { ChatStopButton } from "../chat-stop-button";

interface ChatInputActionsProps {
  readonly disabled: boolean;
  readonly canSubmit: boolean;
  readonly running: boolean;
  readonly handleSubmit: () => void;
  readonly handleCancel: () => void;
}

export function ChatInputActions({
  disabled,
  canSubmit,
  running,
  handleSubmit,
  handleCancel,
}: ChatInputActionsProps) {
  return (
    <div
      data-testid="chat-input-actions"
      className="flex min-h-[var(--oh-control-size-xs)] w-full items-center justify-between gap-[var(--oh-space-3)]"
    >
      <p className="text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
        Enter 发送 · Shift+Enter 换行
      </p>
      {running ? (
        <ChatStopButton handleStop={handleCancel} />
      ) : (
        <ChatSendButton
          handleSubmit={handleSubmit}
          disabled={disabled || !canSubmit}
        />
      )}
    </div>
  );
}
