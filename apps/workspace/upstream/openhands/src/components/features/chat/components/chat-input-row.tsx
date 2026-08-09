import type React from "react";

import { ChatInputField } from "./chat-input-field";

interface ChatInputRowProps {
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled: boolean;
  readonly onInput: () => void;
  readonly onPaste: (event: React.ClipboardEvent) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
  readonly onFocus?: () => void;
  readonly onBlur?: () => void;
}

export function ChatInputRow({
  chatInputRef,
  disabled,
  onInput,
  onPaste,
  onKeyDown,
  onFocus,
  onBlur,
}: ChatInputRowProps) {
  return (
    <div className="flex w-full min-w-0 items-end">
      <ChatInputField
        chatInputRef={chatInputRef}
        disabled={disabled}
        onInput={onInput}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
      />
    </div>
  );
}
