import { CustomChatInput } from "./custom-chat-input";

interface InteractiveChatBoxProps {
  readonly disabled: boolean;
  readonly submitting: boolean;
  readonly onSubmit: (message: string) => Promise<void>;
}

export function InteractiveChatBox({
  disabled,
  submitting,
  onSubmit,
}: InteractiveChatBoxProps) {
  return (
    <div className="shrink-0 px-[var(--oh-space-5)] pb-[var(--oh-space-5)] pt-[var(--oh-space-4)]">
      <CustomChatInput
        disabled={disabled}
        submitting={submitting}
        onSubmit={onSubmit}
      />
    </div>
  );
}
