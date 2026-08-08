import { CommandMenu } from "../components/features/command-menu/command-menu";
import { Sidebar } from "../components/features/sidebar/sidebar";
import type { AgentWorkspaceRuntime } from "../root";

import { ConversationView } from "./conversation";

interface MainAppProps {
  readonly runtime: AgentWorkspaceRuntime;
}

function focusComposer() {
  document.querySelector<HTMLElement>("[data-testid='chat-input']")?.focus();
}

export default function MainApp({ runtime }: MainAppProps) {
  return (
    <div
      data-testid="root-layout"
      className="flex h-dvh min-w-[1024px] overflow-hidden bg-[var(--oh-canvas)] text-[var(--oh-text)]"
    >
      <Sidebar
        onNewTask={focusComposer}
        canStartTask={runtime.availability === "ready"}
      />
      <main id="main-content" tabIndex={-1} className="min-w-0 flex-1">
        <ConversationView runtime={runtime} />
      </main>
      <CommandMenu
        onNewTask={focusComposer}
        canStartTask={runtime.availability === "ready"}
      />
    </div>
  );
}
