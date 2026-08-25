import type { ReactNode } from "react";

import MainApp from "./routes/root-layout";

export { Messages } from "./components/conversation-events/chat/messages";
export { CollapsibleThinking } from "./components/conversation-events/chat/event-message-components/collapsible-thinking";
export { ChatMessage } from "./components/features/chat/chat-message";

/** Typed navigation status derived from server/project state; never parsed from display strings. */
export type ResearchNavigationStatus = "idle" | "running" | "waiting" | "error";

export interface ResearchNavigationItem {
  readonly id: string;
  readonly title: string;
  readonly status: ResearchNavigationStatus;
  readonly current: boolean;
  readonly pinned: boolean;
  /** Recent-access ordering fact for the sidebar Recent group; never rendered. */
  readonly lastAccessedAt: string;
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
    readonly onFilesSelected?: (files: readonly File[]) => void;
    readonly onDragOver?: () => void;
    readonly onDragLeave?: () => void;
    readonly onDropFiles?: (files: readonly File[]) => void;
    readonly dragActive?: boolean;
    readonly onValueChange: (value: string) => void;
    readonly onSubmit: (message: string) => Promise<void>;
  } | null;
  /** Product-owned, server-backed Research Thread projection. */
  readonly threadPanel: ReactNode;
  /** Count of main stream items; drives the scroll-up new-progress counter. */
  readonly threadItemCount: number;
  /** Product-owned global actions rendered in the workspace top bar. */
  readonly headerActions?: ReactNode;
  /** Product-owned Research Inspector content rendered in the docked right rail. */
  readonly inspectorPanel: ReactNode | null;
  /** Optional product detail shown in the same docked right rail. */
  readonly inspectorDockedPanel?: ReactNode | null;
  /** Product-owned navigation rendered in the docked rail header. */
  readonly inspectorDockedToolbar?: ReactNode | null;
  /** Heading for the docked detail. */
  readonly inspectorDockedLabel?: string;
  /**
   * A versioned request to open the docked right rail. The shell consumes a
   * changed key once; subsequent user panel controls remain locally authoritative.
   */
  readonly inspectorRequest?: {
    readonly key: string;
  };
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
