import type React from "react";

import { ChatInputActions } from "./chat-input-actions";
import { ChatInputRow } from "./chat-input-row";

interface ChatInputContainerProps {
  readonly chatContainerRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled: boolean;
  readonly canSubmit: boolean;
  readonly submitting: boolean;
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly handleSubmit: () => void;
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
  submitting,
  chatInputRef,
  handleSubmit,
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
      className="chat-input-container flex h-full min-h-0 w-full flex-col justify-between gap-y-[var(--oh-composer-row-gap)] rounded-[var(--oh-radius-lg)] border border-[var(--oh-border-strong)] bg-transparent px-[var(--oh-composer-padding-inline)] py-[var(--oh-composer-padding-block)]"
    >
      <ChatInputRow
        chatInputRef={chatInputRef}
        disabled={disabled || submitting}
        onInput={onInput}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
      />
      <ChatInputActions
        disabled={disabled}
        canSubmit={canSubmit}
        submitting={submitting}
        handleSubmit={handleSubmit}
      />
    </div>
  );
}
