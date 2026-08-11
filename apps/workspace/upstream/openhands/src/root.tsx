import type { ReactNode } from "react";

import type { ActivityPresentationEvent } from "./components/conversation-events/chat/group-events";
import MainApp from "./routes/root-layout";

export interface ResearchNavigationItem {
  readonly id: string;
  readonly title: string;
  readonly status: string;
  readonly updatedAt: string;
  readonly current: boolean;
}

export interface ResearchWorkspaceRuntime {
  readonly project: {
    readonly name: string;
  } | null;
  readonly run: {
    readonly status: string;
    readonly executionMode: string;
  } | null;
  readonly navigation: {
    readonly projects: readonly ResearchNavigationItem[];
    readonly onOpenProject: (projectId: string) => void;
    readonly onNewResearch: () => void;
    readonly onLogout: () => void;
  };
  readonly composer: {
    readonly canSubmitIntent: boolean;
    readonly submitting: boolean;
    readonly submitIntent: ((intent: string) => Promise<void>) | null;
  };
  readonly activation: {
    readonly title: string;
    readonly description: string;
    readonly actionLabel: string;
    readonly onAction: () => void;
  } | null;
  readonly activityEvents: readonly ActivityPresentationEvent[];
  readonly contextPanel: ReactNode;
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
