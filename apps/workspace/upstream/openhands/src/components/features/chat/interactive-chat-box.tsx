import { CustomChatInput } from "./custom-chat-input";

interface InteractiveChatBoxProps {
  readonly disabled: boolean;
  readonly running: boolean;
  readonly onSubmit: (message: string) => void;
  readonly onCancel: () => void;
}

export function InteractiveChatBox({
  disabled,
  running,
  onSubmit,
  onCancel,
}: InteractiveChatBoxProps) {
  return (
    <div className="shrink-0 px-[var(--oh-space-5)] pb-[var(--oh-space-5)] pt-[var(--oh-space-4)]">
      <CustomChatInput
        disabled={disabled}
        running={running}
        onSubmit={onSubmit}
        onCancel={onCancel}
      />
    </div>
  );
}
