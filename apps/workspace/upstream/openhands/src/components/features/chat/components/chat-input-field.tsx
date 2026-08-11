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
        className="chat-input min-h-[var(--oh-composer-input-min-block-size)] max-h-[var(--oh-composer-input-max-block-size)] overflow-y-auto whitespace-pre-wrap bg-transparent text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-text)] outline-none"
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-label="输入研究意图"
        aria-multiline="true"
        aria-disabled={disabled}
        data-placeholder="描述希望研究的问题、对象与预期结果"
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
