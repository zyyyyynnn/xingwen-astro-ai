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
    <div className="shrink-0 px-5 pb-5 pt-4">
      <CustomChatInput
        disabled={disabled}
        running={running}
        onSubmit={onSubmit}
        onCancel={onCancel}
      />
    </div>
  );
}
