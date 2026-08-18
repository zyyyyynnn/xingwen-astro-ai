import { useQuery } from "@tanstack/react-query";
import type { DomainEntityId } from "@xingwen/domain";
import type { ResearchArtifactViewModel } from "@xingwen/research-adapter";
import { Alert, AlertDescription, Button } from "@xingwen/ui";
import { FileCheck2 } from "@xingwen/ui/icons";
import { useMemo, type ReactNode } from "react";

import type { ResearchWorkspaceRuntime } from "../../upstream/openhands/src/root";
import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { ArtifactFullscreenWorkspace } from "./artifact-fullscreen-workspace";

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
  artifacts,
  onOpen,
}: {
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

  if (visible.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        研究任务尚未产出正式结果。
      </p>
    );
  }

  return (
    <ol className="space-y-1" aria-label="研究结果">
      {visible.map((artifact) => (
        <li key={artifact.id}>
          <Button
            variant="ghost"
            onClick={() => onOpen(artifact.latestVersionId)}
            className="flex h-auto w-full items-center justify-between gap-3 px-2 py-2 text-left"
          >
            <span className="flex min-w-0 items-center gap-2">
              <FileCheck2
                className="size-4 shrink-0 text-muted-foreground"
                aria-hidden="true"
              />
              <span className="truncate text-sm font-medium text-foreground">
                {artifact.title}
              </span>
            </span>
            <span className="shrink-0 text-xs text-muted-foreground">
              查看完整结果 →
            </span>
          </Button>
        </li>
      ))}
    </ol>
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
    <div className="artifact-overview p-4">
      {artifacts.isError ? (
        <ArtifactLoadError message={publicError(runtime, artifacts.error)} />
      ) : null}
      <ArtifactResultIndex
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
