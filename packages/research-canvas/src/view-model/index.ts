import type { DomainEntityId } from "@xingwen/domain";

export interface MissionNavigationViewModel {
  readonly pinnedProjects: readonly string[];
  readonly recentProjects: readonly string[];
  readonly projects: readonly {
    readonly id: string;
    readonly name: string;
    readonly userStatus: "running" | "needs_review" | "completed" | "failed" | "draft";
    readonly updatedAt: string;
  }[];
}

export interface MissionHeaderViewModel {
  readonly projectId: string;
  readonly projectName: string;
  readonly runId: string | null;
  readonly status: "idle" | "running" | "waiting_for_input" | "completed" | "failed" | "cancelled" | null;
  readonly executionMode: "auto" | "interactive" | "fast" | "fixture" | null;
}

export interface MissionLifecycleViewModel {
  readonly currentPhase: "brief" | "active" | "source_review" | "completion";
  readonly progress: number;
}

export interface CompletionSummaryViewModel {
  readonly researchGoal: string | null;
  readonly status: "completed" | "failed" | "cancelled";
  readonly conclusion: string | null;
  readonly findings: readonly {
    readonly statementId: DomainEntityId;
    readonly text: string;
    readonly evidenceIds: readonly DomainEntityId[];
    readonly status: "supported" | "unsupported" | "unverifiable";
  }[];
  readonly limitations: readonly {
    readonly statementId: DomainEntityId;
    readonly text: string;
    readonly evidenceIds: readonly DomainEntityId[];
    readonly status: "supported" | "unsupported" | "unverifiable";
  }[];
  readonly futureWork: readonly {
    readonly statementId: DomainEntityId;
    readonly text: string;
    readonly evidenceIds: readonly DomainEntityId[];
    readonly status: "supported" | "unsupported" | "unverifiable";
  }[];
  readonly unresolvedQuestions: readonly string[];
  readonly nextSteps: readonly string[];
  readonly finalArtifactId: string | null;
  readonly finalArtifactTitle: string | null;
  readonly hasReproducibility: boolean;
  readonly isDeriveMissionAvailable: boolean;
}

export interface ArtifactReviewViewModel {
  readonly artifactId: string;
  readonly title: string;
  readonly kind: string;
  readonly version: number;
  readonly status: string;
  readonly content: React.ReactNode;
  readonly isReviewAvailable: boolean;
  readonly isSourceAvailable: boolean;
  readonly isCompareAvailable: boolean;
  readonly isExportAvailable: boolean;
}

export interface SourceReviewViewModel {
  readonly availableExtracts: readonly {
    readonly text: string;
    readonly location: string;
  }[];
  readonly isFullSourceAvailable: boolean;
  readonly missingContractMessage: string | null;
}

export type MainStageViewModel =
  | { type: "completion"; data: CompletionSummaryViewModel }
  | { type: "artifact"; data: ArtifactReviewViewModel }
  | { type: "source"; data: SourceReviewViewModel };

export interface ResearchContextViewModel {
  readonly mode: "hidden" | "summary" | "detail";
  readonly summaries: readonly {
    readonly type: "final_artifact" | "evidence" | "reproducibility";
    readonly title: string;
    readonly description: string;
    readonly isComplete: boolean;
  }[];
  readonly detailContent: React.ReactNode | null;
}

export interface ResearchComposerViewModel {
  readonly mode: "docked" | "focus";
  readonly isAvailable: boolean;
}

export interface ResearchCanvasViewModel {
  readonly navigation: MissionNavigationViewModel;
  readonly mission: MissionHeaderViewModel;
  readonly lifecycle: MissionLifecycleViewModel;
  readonly stage: MainStageViewModel;
  readonly context: ResearchContextViewModel;
  readonly composer: ResearchComposerViewModel;
}
