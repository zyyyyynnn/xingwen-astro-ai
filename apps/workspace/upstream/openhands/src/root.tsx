import type { ReactNode } from "react";

import MainApp from "./routes/root-layout";

export { Messages } from "./components/conversation-events/chat/messages";
export { CollapsibleRationale } from "./components/conversation-events/chat/event-message-components/collapsible-thinking";
export { NarrativeDisclosure } from "./components/conversation-events/chat/event-message-components/collapsible-thinking";
export { ChatMessage } from "./components/features/chat/chat-message";

export interface ResearchNavigationItem {
  readonly id: string;
  readonly title: string;
  readonly status: string;
  readonly updatedAt: string;
  readonly current: boolean;
  readonly pinned: boolean;
}

export interface ResearchWorkspaceRuntime {
  readonly project: {
    readonly name: string;
    readonly statusLabel: string;
  } | null;
  readonly navigation: {
    readonly projects: readonly ResearchNavigationItem[];
    readonly onOpenProject: (projectId: string) => void;
    readonly onNewResearch: () => void;
    readonly onReturnHome: () => void;
    readonly onToggleProjectPinned: (projectId: string) => void;
    readonly onRequestProjectRename: (projectId: string) => void;
    readonly onRequestProjectDelete: (projectId: string) => void;
  };
  readonly composer: {
    readonly submitting: boolean;
    readonly value: string;
    readonly placeholder: string;
    readonly hasStartedConversation: boolean;
    readonly leadingActions: ReactNode;
    readonly beforeInput: ReactNode;
    readonly onValueChange: (value: string) => void;
    readonly onSubmit: (message: string) => Promise<void>;
  } | null;
  readonly activation: {
    readonly title: string;
    readonly description: string;
    readonly actionLabel: string;
    readonly onAction: () => void;
  } | null;
  /** Product-owned, server-backed Research Thread projection. */
  readonly threadPanel: ReactNode;
  /** Product-owned floating/docked Research Inspector projection. */
  readonly inspectorPanel: ReactNode | null;
}

interface OpenHandsWorkspaceRootProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

/** Source-adopted OpenHands mechanics with Xingwen research presentation data. */
export function OpenHandsWorkspaceRoot({
  runtime,
}: OpenHandsWorkspaceRootProps) {
  return <MainApp runtime={runtime} />;
}

export default OpenHandsWorkspaceRoot;
