import { ChatInterface } from "../../chat/chat-interface";
import type { AgentWorkspaceRuntime } from "../../../../root";

interface ChatInterfaceWrapperProps {
  readonly runtime: AgentWorkspaceRuntime;
}

/** OpenHands' conversation seam with the product-specific execution boundary injected. */
export function ChatInterfaceWrapper({ runtime }: ChatInterfaceWrapperProps) {
  return (
    <div
      data-testid="workspace-main-surface"
      className="flex h-full min-h-0 w-full justify-center bg-[var(--oh-canvas)]"
    >
      <div className="flex h-full min-h-0 w-full min-w-0 max-w-[var(--oh-content-max-inline-size)] flex-col">
        <ChatInterface runtime={runtime} />
      </div>
    </div>
  );
}
