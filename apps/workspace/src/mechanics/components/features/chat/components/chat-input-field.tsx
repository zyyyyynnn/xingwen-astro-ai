import type React from "react";

interface ChatInputFieldProps {
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled?: boolean;
  readonly placeholder: string;
  readonly onInput: () => void;
  readonly onPaste: (event: React.ClipboardEvent) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
}

export function ChatInputField({
  chatInputRef,
  disabled = false,
  placeholder,
  onInput,
  onPaste,
  onKeyDown,
}: ChatInputFieldProps) {
  return (
    <div className="min-w-0 flex-1">
      <div
        ref={chatInputRef}
        className="chat-input min-h-[var(--workspace-composer-input-min-block-size)] max-h-[var(--workspace-composer-input-max-block-size)] overflow-y-auto whitespace-pre-wrap bg-transparent text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)] text-[var(--color-ink-primary)] outline-none"
        contentEditable={!disabled}
        suppressContentEditableWarning
        role="textbox"
        aria-label="输入研究消息"
        aria-multiline="true"
        aria-disabled={disabled}
        data-placeholder={placeholder}
        data-testid="chat-input"
        onInput={onInput}
        onPaste={onPaste}
        onKeyDown={onKeyDown}
      />
    </div>
  );
}
