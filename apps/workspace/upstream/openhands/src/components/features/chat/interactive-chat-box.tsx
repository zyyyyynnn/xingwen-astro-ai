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
      />
    </div>
  );
}
