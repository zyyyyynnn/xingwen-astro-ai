import { ChatInterface } from "../../chat/chat-interface";
import type { ResearchWorkspaceRuntime } from "../../../../root";

interface ChatInterfaceWrapperProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

/** Workspace conversation seam with the product execution boundary injected. */
export function ChatInterfaceWrapper({ runtime }: ChatInterfaceWrapperProps) {
  return (
    <div
      data-testid="workspace-main-surface"
      className="flex h-full min-h-0 w-full bg-[var(--color-canvas)]"
    >
      <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
        <ChatInterface runtime={runtime} />
      </div>
    </div>
  );
}
