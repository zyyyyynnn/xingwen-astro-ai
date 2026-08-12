import type { ReactNode } from "react";

import { ChatSendButton } from "../chat-send-button";

interface ChatInputActionsProps {
  readonly disabled: boolean;
  readonly canSubmit: boolean;
  readonly submitting: boolean;
  readonly leadingActions: ReactNode;
  readonly handleSubmit: () => void;
}

export function ChatInputActions({
  disabled,
  canSubmit,
  submitting,
  leadingActions,
  handleSubmit,
}: ChatInputActionsProps) {
  return (
    <div
      data-testid="chat-input-actions"
      className="flex min-h-[var(--oh-control-size-xs)] w-full items-center justify-between gap-[var(--oh-space-3)]"
    >
      <div className="flex min-w-0 items-center gap-[var(--oh-space-2)]">
        {leadingActions}
      </div>
      <ChatSendButton
        handleSubmit={handleSubmit}
        disabled={disabled || !canSubmit || submitting}
        submitting={submitting}
      />
    </div>
  );
}
