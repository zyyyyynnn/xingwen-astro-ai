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
    <div className="flex h-6 w-full items-center justify-between gap-3">
      <p className="text-xs text-[var(--oh-text-dim)]">
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
