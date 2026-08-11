import { CommandMenu } from "../components/features/command-menu/command-menu";
import { Sidebar } from "../components/features/sidebar/sidebar";
import type { ResearchWorkspaceRuntime } from "../root";

import { ConversationView } from "./conversation";

interface MainAppProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

export default function MainApp({ runtime }: MainAppProps) {
  return (
    <div
      data-testid="root-layout"
      className="flex h-dvh min-w-[var(--oh-min-inline-size)] overflow-hidden bg-[var(--oh-canvas)] text-[var(--oh-text)]"
    >
      <Sidebar
        projects={runtime.navigation.projects}
        onOpenProject={runtime.navigation.onOpenProject}
        onNewResearch={runtime.navigation.onNewResearch}
        onLogout={runtime.navigation.onLogout}
      />
      <main id="main-content" tabIndex={-1} className="min-w-0 flex-1">
        <ConversationView runtime={runtime} />
      </main>
      <CommandMenu onNewResearch={runtime.navigation.onNewResearch} />
    </div>
  );
}
