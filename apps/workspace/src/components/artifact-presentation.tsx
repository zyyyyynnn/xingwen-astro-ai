import { useQuery, useQueries } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import type { ResearchArtifactViewModel } from "@xingwen/research-adapter";
import { Alert, AlertDescription } from "@xingwen/ui";
import { useMemo, type ReactNode } from "react";

import type { ResearchWorkspaceRuntime } from "../mechanics/root";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { artifactKindLabel } from "../presentation/artifact-presentation-labels";
import { artifactResultSummary } from "../presentation/artifact-result-summary";
import { resolveArtifactRenderer } from "../presentation/artifact-renderer-registry";
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
      <div className="py-8 text-center text-xs artifact-results__note">
        研究任务尚未产出正式结果。
      </div>
    );
  }

  const indexed = visible.map((artifact, index) => ({
    artifact,
    versionData: versionQueries[index]?.data,
  }));
  const reviewItems = indexed.filter(({ artifact, versionData }) => {
    if (artifact.kind !== "literature_relations") return false;
    return Boolean(
      versionData?.presentation.entries?.some(
        (entry) => entry.status === "candidate",
      ),
    );
  });
  const ordinaryItems = indexed.filter((item) => !reviewItems.includes(item));

  const renderItem = ({ artifact, versionData }: (typeof indexed)[number]) => {
    const kindLabel = artifactKindLabel(artifact.kind);
    const evidenceCount = versionData?.provenance.evidenceIds.length ?? 0;
    const fallbackSummary = versionData
      ? artifactResultSummary(versionData.presentation)
      : evidenceCount > 0
        ? `证据 ${evidenceCount} 条`
        : null;
    const descriptor = resolveArtifactRenderer(artifact.kind);
    const reviewCount =
      artifact.kind === "literature_relations"
        ? (versionData?.presentation.entries?.filter(
            (entry) => entry.status === "candidate",
          ).length ?? 0)
        : 0;

    const row = (metadataSummary: string | null) => (
      <ResultIndexItem
        key={artifact.id}
        artifactId={artifact.id}
        latestVersionId={artifact.latestVersionId}
        kind={artifact.kind}
        kindLabel={kindLabel}
        title={artifact.title}
        metadataSummary={metadataSummary}
        statusLabel={reviewCount > 0 ? `${reviewCount} 待审` : null}
        statusVariant={reviewCount > 0 ? "outline" : undefined}
        onOpen={onOpen}
      />
    );

    if (!descriptor) return row(fallbackSummary);
    const SummaryRenderer = descriptor.SummaryRenderer;
    return (
      <SummaryRenderer
        key={artifact.id}
        runtime={runtime}
        projectId={projectId}
        artifact={artifact}
        versionId={artifact.latestVersionId}
      >
        {(summary) => row(summary ?? fallbackSummary)}
      </SummaryRenderer>
    );
  };

  return (
    <div className="space-y-4" aria-label="研究结果">
      {reviewItems.length > 0 ? (
        <section aria-labelledby="review-results-title">
          <h3
            id="review-results-title"
            className="ui-text-label mb-1 font-medium"
          >
            需要处理 · {reviewItems.length}
          </h3>
          <div>{reviewItems.map(renderItem)}</div>
        </section>
      ) : null}
      <section aria-labelledby="all-results-title">
        <h3
          id="all-results-title"
          className="ui-text-label mb-1 font-medium artifact-results__note"
        >
          研究结果 · {ordinaryItems.length}
        </h3>
        <div>{ordinaryItems.map(renderItem)}</div>
      </section>
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
