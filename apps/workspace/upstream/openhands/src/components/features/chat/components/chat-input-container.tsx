import type React from "react";

import { ChatInputActions } from "./chat-input-actions";
import { ChatInputRow } from "./chat-input-row";

interface ChatInputContainerProps {
  readonly chatContainerRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled: boolean;
  readonly canSubmit: boolean;
  readonly running: boolean;
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly handleSubmit: () => void;
  readonly handleCancel: () => void;
  readonly onInput: () => void;
  readonly onPaste: (event: React.ClipboardEvent) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
  readonly onFocus?: () => void;
  readonly onBlur?: () => void;
}

export function ChatInputContainer({
  chatContainerRef,
  disabled,
  canSubmit,
  running,
  chatInputRef,
  handleSubmit,
  handleCancel,
  onInput,
  onPaste,
  onKeyDown,
  onFocus,
  onBlur,
}: ChatInputContainerProps) {
  return (
    <div
      ref={chatContainerRef}
      data-testid="chat-input-container"
      className="flex h-full min-h-14 w-full flex-col justify-between rounded-[var(--oh-radius-lg)] border border-[var(--oh-border-strong)] bg-transparent p-2.5"
    >
      <ChatInputRow
        chatInputRef={chatInputRef}
        disabled={disabled || running}
        onInput={onInput}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
      />
      <ChatInputActions
        disabled={disabled}
        canSubmit={canSubmit}
        running={running}
        handleSubmit={handleSubmit}
        handleCancel={handleCancel}
      />
    </div>
  );
}
