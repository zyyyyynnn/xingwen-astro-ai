import type { ReactNode } from "react";

import { CustomChatInput } from "./custom-chat-input";

interface InteractiveChatBoxProps {
  readonly value: string;
  readonly disabled: boolean;
  readonly submitting: boolean;
  readonly placeholder: string;
  readonly leadingActions: ReactNode;
  readonly hasStartedConversation: boolean;
  readonly onValueChange: (value: string) => void;
  readonly onSubmit: (message: string) => Promise<void>;
  readonly onFilesSelected?: (files: readonly File[]) => void;
  readonly onDragOver?: () => void;
  readonly onDragLeave?: () => void;
  readonly onDropFiles?: (files: readonly File[]) => void;
  readonly dragActive?: boolean;
}

/** OpenHands InteractiveChatBox with research-domain actions injected. */
export function InteractiveChatBox({
  value,
  disabled,
  submitting,
  placeholder,
  leadingActions,
  onValueChange,
  onSubmit,
  onFilesSelected,
  onDragOver,
  onDragLeave,
  onDropFiles,
  dragActive,
}: InteractiveChatBoxProps) {
  return (
    <div data-testid="interactive-chat-box">
      <CustomChatInput
        value={value}
        disabled={disabled}
        submitting={submitting}
        placeholder={placeholder}
        leadingActions={leadingActions}
        onValueChange={onValueChange}
        onSubmit={onSubmit}
        onFilesSelected={onFilesSelected}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDropFiles={onDropFiles}
        dragActive={dragActive}
      />
    </div>
  );
}
