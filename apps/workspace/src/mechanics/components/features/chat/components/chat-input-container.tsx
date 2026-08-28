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
  readonly onDragOver?: () => void;
  readonly onDragLeave?: () => void;
  readonly onDrop: (event: React.DragEvent<HTMLDivElement>) => void;
  readonly dragActive: boolean;
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
  onDragOver,
  onDragLeave,
  onDrop,
  dragActive,
}: ChatInputContainerProps) {
  return (
    <div
      ref={chatContainerRef}
      data-testid="chat-input-container"
      className={`chat-input-container flex h-full min-h-0 w-full flex-col justify-between gap-y-[var(--workspace-composer-row-gap)] rounded-[var(--radius-lg)] border bg-[var(--color-surface)] px-[var(--workspace-composer-padding-inline)] py-[var(--workspace-composer-padding-block)] transition-colors focus-within:border-[var(--color-border-strong)] ${dragActive ? "border-[var(--color-border-strong)] bg-[var(--color-surface-hover)]" : "border-[var(--color-border)]"}`}
      onDragOver={(event) => {
        event.preventDefault();
        onDragOver?.();
      }}
      onDragLeave={onDragLeave}
      onDrop={onDrop}
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
