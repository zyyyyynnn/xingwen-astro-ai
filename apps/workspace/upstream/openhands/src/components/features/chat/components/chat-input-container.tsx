import type React from "react";
import type { ReactNode } from "react";

import { ChatInputActions } from "./chat-input-actions";
import { ChatInputRow } from "./chat-input-row";

interface ChatInputContainerProps {
  readonly chatContainerRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled: boolean;
  readonly canSubmit: boolean;
  readonly submitting: boolean;
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly placeholder: string;
  readonly leadingActions: ReactNode;
  readonly handleSubmit: () => void;
  readonly onInput: () => void;
  readonly onPaste: (event: React.ClipboardEvent) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
}

export function ChatInputContainer({
  chatContainerRef,
  disabled,
  canSubmit,
  submitting,
  chatInputRef,
  placeholder,
  leadingActions,
  handleSubmit,
  onInput,
  onPaste,
  onKeyDown,
}: ChatInputContainerProps) {
  return (
    <div
      ref={chatContainerRef}
      data-testid="chat-input-container"
      className="chat-input-container flex h-full min-h-0 w-full flex-col justify-between gap-y-[var(--oh-composer-row-gap)] rounded-[var(--oh-radius-lg)] border border-[var(--oh-border)] bg-[var(--oh-surface)] px-[var(--oh-composer-padding-inline)] py-[var(--oh-composer-padding-block)] transition-colors focus-within:border-[var(--oh-border-strong)]"
    >
      <ChatInputRow
        chatInputRef={chatInputRef}
        disabled={disabled || submitting}
        placeholder={placeholder}
        onInput={onInput}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
      />
      <ChatInputActions
        disabled={disabled}
        canSubmit={canSubmit}
        submitting={submitting}
        leadingActions={leadingActions}
        handleSubmit={handleSubmit}
      />
    </div>
  );
}
