import type React from "react";

import { ChatInputField } from "./chat-input-field";

interface ChatInputRowProps {
  readonly chatInputRef: React.RefObject<HTMLDivElement | null>;
  readonly disabled: boolean;
  readonly placeholder: string;
  readonly onInput: () => void;
  readonly onPaste: (event: React.ClipboardEvent) => void;
  readonly onKeyDown: (event: React.KeyboardEvent) => void;
}

export function ChatInputRow(props: ChatInputRowProps) {
  return (
    <div className="flex w-full min-w-0 items-end">
      <ChatInputField {...props} />
    </div>
  );
}
