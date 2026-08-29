import { useQuery, useQueries } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import type { ResearchArtifactViewModel } from "@xingwen/research-adapter";
import { Alert, AlertDescription } from "@xingwen/ui";
import { useMemo, type ReactNode } from "react";

import type { ResearchWorkspaceRuntime } from "../mechanics/root";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { artifactKindLabel } from "../presentation/artifact-presentation-labels";
import { artifactResultSummary } from "../presentation/artifact-result-summary";
import { ArtifactFullscreenWorkspace } from "./artifact-fullscreen-workspace";
import { ResultIndexItem } from "./result-layout";

export interface ResearchThreadProjection {
  readonly id: string;
  readonly occurredAt: string;
  readonly node: ReactNode;
}

interface ArtifactPresentationOptions {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly runId: DomainEntityId | null;
  readonly artifactVersionId: DomainEntityId | null;
  readonly onOpenArtifactVersion: (artifactVersionId: DomainEntityId) => void;
  readonly onReturnToOverview: () => void;
}

function publicError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

function ArtifactLoadError({ message }: { readonly message: string }) {
  return (
    <Alert variant="destructive">
      <AlertDescription>{message}</AlertDescription>
    </Alert>
  );
}

function ArtifactResultIndex({
  projectId,
  runtime,
  artifacts,
  onOpen,
}: {
  readonly projectId: DomainEntityId;
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly artifacts: readonly ResearchArtifactViewModel[];
  readonly onOpen: (artifactVersionId: DomainEntityId) => void;
}) {
  const visible = artifacts.filter(
    (
      artifact,
    ): artifact is ResearchArtifactViewModel & {
      readonly latestVersionId: DomainEntityId;
    } => artifact.latestVersionId !== null,
  );

  const versionQueries = useQueries({
    queries: visible.slice(0, 8).map((artifact) => ({
      ...runtime.application.queries.artifactVersion(
        projectId,
        artifact.latestVersionId,
      ),
      staleTime: 60_000,
    })),
  });

  if (visible.length === 0) {
    return (
      <div className="py-8 text-center text-xs text-muted-foreground">
        研究任务尚未产出正式结果。
      </div>
    );
  }

  return (
    <div className="space-y-1" aria-label="研究结果">
      {visible.map((artifact, index) => {
        const versionData = versionQueries[index]?.data;
        const kindLabel = artifactKindLabel(artifact.kind);
        const evidenceCount = versionData?.provenance.evidenceIds.length ?? 0;
        const scientificSummary = versionData
          ? artifactResultSummary(versionData.presentation)
          : null;
        const metadataSummary =
          scientificSummary ??
          (evidenceCount > 0 ? `证据 ${evidenceCount} 条` : null);

        return (
          <ResultIndexItem
            key={artifact.id}
            artifactId={artifact.id}
            latestVersionId={artifact.latestVersionId}
            kind={artifact.kind}
            kindLabel={kindLabel}
            title={artifact.title}
            metadataSummary={metadataSummary}
            onOpen={onOpen}
          />
        );
      })}
    </div>
  );
}

export function useArtifactPresentation({
  runtime,
  projectId,
  runId,
  artifactVersionId,
  onOpenArtifactVersion,
  onReturnToOverview,
}: ArtifactPresentationOptions): {
  readonly threadProjections: readonly ResearchThreadProjection[];
  readonly hasArtifacts: boolean;
  readonly artifactCount: number;
  readonly resultPanel: ReactNode;
  readonly inspectorDockedPanel: ReactNode;
  readonly inspectorDockedLabel: string;
  readonly inspectorRequest: NonNullable<
    ResearchWorkspaceRuntime["inspectorRequest"]
  >;
  readonly fullscreenDialog: ReactNode;
} {
  const artifacts = useQuery({
    ...runtime.application.queries.artifactsByRun(
      projectId,
      runId ?? projectId,
    ),
    enabled: runId !== null,
  });

  // Inspector visibility is a user preference. Result routing never mutates it.
  const inspectorRequest = useMemo<
    NonNullable<ResearchWorkspaceRuntime["inspectorRequest"]>
  >(() => ({ key: "workspace-overview" }), []);

  const artifactList = artifacts.data ?? [];
  const resultPanel = (
    <div className="artifact-overview p-3">
      {artifacts.isError ? (
        <ArtifactLoadError message={publicError(runtime, artifacts.error)} />
      ) : null}
      <ArtifactResultIndex
        projectId={projectId}
        runtime={runtime}
        artifacts={artifactList}
        onOpen={onOpenArtifactVersion}
      />
    </div>
  );

  const fullscreenDialog =
    artifactVersionId === null ? null : (
      <ArtifactFullscreenWorkspace
        runtime={runtime}
        projectId={projectId}
        artifactVersionId={artifactVersionId}
        onClose={onReturnToOverview}
        onOpenArtifactVersion={onOpenArtifactVersion}
      />
    );

  return {
    threadProjections: [],
    hasArtifacts: artifactList.length > 0,
    artifactCount: artifactList.length,
    resultPanel,
    inspectorDockedPanel: null,
    inspectorDockedLabel: "研究概览",
    inspectorRequest,
    fullscreenDialog,
  };
}
