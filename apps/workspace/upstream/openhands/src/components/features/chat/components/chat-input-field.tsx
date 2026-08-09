import type React from "react";

interface ChatInputFieldProps {
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled?: boolean;
  readonly onInput: () => void;
  readonly onPaste: (event: React.ClipboardEvent) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
  readonly onFocus?: () => void;
  readonly onBlur?: () => void;
}

export function ChatInputField({
  chatInputRef,
  disabled = false,
  onInput,
  onPaste,
  onKeyDown,
  onFocus,
  onBlur,
}: ChatInputFieldProps) {
  return (
    <div className="min-w-0 flex-1">
      <div
        ref={chatInputRef}
        className="chat-input min-h-5 max-h-[calc(15rem-3.5rem)] overflow-y-auto whitespace-pre-wrap bg-transparent text-sm leading-5 text-[var(--oh-text)] outline-none"
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-label="向 Agent 发送指令"
        aria-multiline="true"
        aria-disabled={disabled}
        data-placeholder="描述需要 Agent 完成的任务"
        data-testid="chat-input"
        onInput={onInput}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
        onFocus={onFocus}
        onBlur={onBlur}
      />
    </div>
  );
}
