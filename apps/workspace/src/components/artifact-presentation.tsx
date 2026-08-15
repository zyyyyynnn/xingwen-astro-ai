import { useQuery } from "@tanstack/react-query";
import type { ArtifactKind, DomainEntityId } from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchArtifactViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Button,
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  Separator,
  Skeleton,
} from "@xingwen/ui";
import { ChevronLeft, ChevronRight } from "@xingwen/ui/icons";
import { useState, type ReactNode } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import {
  ARTIFACT_CARD_COPY,
  artifactKindDescription,
  artifactKindLabel,
} from "../presentation/artifact-presentation-labels";
import { resolveArtifactRenderer } from "../presentation/artifact-renderer-registry";
import type { ResearchThreadProjection } from "./research-thread";
import { EvidenceInspector } from "./evidence-inspector";

interface ArtifactPresentationOptions {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly runId: DomainEntityId | null;
  readonly runCompleted: boolean;
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

interface SupportedArtifactProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly onOpenFullscreen: (() => void) | null;
  readonly placement: "thread" | "docked" | "fullscreen";
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
}

function SupportedArtifact({
  runtime,
  projectId,
  artifact,
  version,
  onOpenFullscreen,
  placement,
  onSelectEvidence,
}: SupportedArtifactProps) {
  const registration = resolveArtifactRenderer(artifact.kind);
  const Content = registration.Content;
  return (
    <Content
      runtime={runtime}
      projectId={projectId}
      artifact={artifact}
      version={version}
      placement={placement}
      onOpenFullscreen={onOpenFullscreen}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function ArtifactVersionBoundary({
  runtime,
  projectId,
  artifactVersionId,
  placement,
  onOpenFullscreen,
  onSelectEvidence,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly placement: "docked" | "fullscreen";
  readonly onOpenFullscreen: (() => void) | null;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
}) {
  const version = useQuery(
    runtime.application.queries.artifactVersion(projectId, artifactVersionId),
  );
  if (version.isPending) {
    return <Skeleton className="artifact-presentation__skeleton" />;
  }
  if (version.isError) {
    return <ArtifactLoadError message={publicError(runtime, version.error)} />;
  }
  return (
    <ArtifactBoundary
      runtime={runtime}
      projectId={projectId}
      version={version.data}
      placement={placement}
      onOpenFullscreen={onOpenFullscreen}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function ArtifactBoundary({
  runtime,
  projectId,
  version,
  placement,
  onOpenFullscreen,
  onSelectEvidence,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly placement: "docked" | "fullscreen";
  readonly onOpenFullscreen: (() => void) | null;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
}) {
  const artifact = useQuery(
    runtime.application.queries.artifact(projectId, version.artifactId),
  );
  if (artifact.isPending) {
    return <Skeleton className="artifact-presentation__skeleton" />;
  }
  if (artifact.isError) {
    return <ArtifactLoadError message={publicError(runtime, artifact.error)} />;
  }
  return (
    <SupportedArtifact
      runtime={runtime}
      projectId={projectId}
      artifact={artifact.data}
      version={version}
      placement={placement}
      onOpenFullscreen={onOpenFullscreen}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

function SupportedArtifactThreadContent({
  runtime,
  projectId,
  artifact,
  versionId,
  onSelectEvidence,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly versionId: DomainEntityId;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
}) {
  const version = useQuery(
    runtime.application.queries.artifactVersion(projectId, versionId),
  );
  if (version.isPending) {
    return <Skeleton className="artifact-presentation__skeleton" />;
  }
  if (version.isError) {
    return <ArtifactLoadError message={publicError(runtime, version.error)} />;
  }
  return (
    <SupportedArtifact
      runtime={runtime}
      projectId={projectId}
      artifact={artifact}
      version={version.data}
      placement="thread"
      onOpenFullscreen={null}
      onSelectEvidence={onSelectEvidence}
    />
  );
}

const ARTIFACT_ORDER: readonly ArtifactKind[] = [
  "dataset",
  "field_dictionary",
  "source_collection",
  "spectrum",
  "light_curve",
  "paper_collection",
  "paper_summary",
  "literature_claims",
  "literature_relations",
  "reasoning_traces",
  "graph",
  "export",
];

function ArtifactMetadataThreadContent({
  artifact,
}: {
  readonly artifact: ResearchArtifactViewModel;
}) {
  return (
    <CardContent className="min-h-[7.75rem]">
      <p className="m-0 text-xs text-[var(--oh-muted)]">
        {ARTIFACT_CARD_COPY.description}
      </p>
      <p className="mb-0 mt-[var(--oh-space-1)] text-sm leading-6 text-[var(--oh-muted)]">
        {artifactKindDescription(artifact.kind)}
      </p>
    </CardContent>
  );
}

function MissingArtifactVersionContent() {
  return (
    <CardContent className="min-h-[7.75rem]">
      <p className="m-0 text-xs text-[var(--oh-muted)]">
        {ARTIFACT_CARD_COPY.description}
      </p>
      <p className="mb-0 mt-[var(--oh-space-1)] text-sm leading-6 text-[var(--oh-muted)]">
        {ARTIFACT_CARD_COPY.missingContent}
      </p>
    </CardContent>
  );
}

function ArtifactThreadCard({
  runtime,
  projectId,
  artifacts,
  onOpen,
  onSelectEvidence,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifacts: readonly ResearchArtifactViewModel[];
  readonly onOpen: (artifactVersionId: DomainEntityId) => void;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
}) {
  const orderedArtifacts = [...artifacts].sort(
    (left, right) =>
      ARTIFACT_ORDER.indexOf(left.kind) - ARTIFACT_ORDER.indexOf(right.kind),
  );
  const defaultIndex = Math.max(
    0,
    orderedArtifacts.findIndex((artifact) => artifact.kind === "paper_summary"),
  );
  const [selectedArtifactId, setSelectedArtifactId] =
    useState<DomainEntityId | null>(orderedArtifacts[defaultIndex]?.id ?? null);
  const requestedIndex = orderedArtifacts.findIndex(
    (artifact) => artifact.id === selectedArtifactId,
  );
  const selectedIndex = requestedIndex >= 0 ? requestedIndex : defaultIndex;

  const selectedArtifact = orderedArtifacts[selectedIndex];
  if (!selectedArtifact) return null;
  const selectedRegistration = resolveArtifactRenderer(selectedArtifact.kind);
  const selectedVersionId = selectedArtifact.latestVersionId;

  return (
    <Card
      size="small"
      className="my-[var(--oh-space-3)]"
      aria-label={ARTIFACT_CARD_COPY.ariaLabel}
    >
      <CardHeader>
        <CardDescription>{ARTIFACT_CARD_COPY.eyebrow}</CardDescription>
        <CardTitle role="heading" aria-level={2}>
          {artifactKindLabel(selectedArtifact.kind)}
        </CardTitle>
        <CardAction>
          <div className="flex items-center gap-[var(--oh-space-1)]">
            <span
              className="min-w-[7.5rem] text-center text-xs text-[var(--oh-muted)]"
              aria-live="polite"
            >
              {ARTIFACT_CARD_COPY.position(selectedIndex + 1, artifacts.length)}
            </span>
            <Button
              variant="ghost"
              size="icon"
              aria-label={ARTIFACT_CARD_COPY.previous}
              disabled={selectedIndex === 0}
              onClick={() =>
                setSelectedArtifactId(
                  orderedArtifacts[selectedIndex - 1]?.id ?? null,
                )
              }
            >
              <ChevronLeft data-icon="inline-start" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              aria-label={ARTIFACT_CARD_COPY.next}
              disabled={selectedIndex >= orderedArtifacts.length - 1}
              onClick={() =>
                setSelectedArtifactId(
                  orderedArtifacts[selectedIndex + 1]?.id ?? null,
                )
              }
            >
              <ChevronRight data-icon="inline-end" aria-hidden="true" />
            </Button>
          </div>
        </CardAction>
      </CardHeader>
      <div aria-live="polite" data-artifact-id={selectedArtifact.id}>
        {selectedVersionId === null ? (
          <MissingArtifactVersionContent />
        ) : selectedRegistration.capability === "supported" ? (
          <SupportedArtifactThreadContent
            runtime={runtime}
            projectId={projectId}
            artifact={selectedArtifact}
            versionId={selectedVersionId}
            onSelectEvidence={onSelectEvidence}
          />
        ) : (
          <ArtifactMetadataThreadContent artifact={selectedArtifact} />
        )}
      </div>
      {selectedVersionId !== null &&
      selectedRegistration.capability === "supported" ? (
        <CardFooter className="justify-end">
          <Button
            variant="secondary"
            size="small"
            onClick={() => onOpen(selectedVersionId)}
          >
            {ARTIFACT_CARD_COPY.openReport}
          </Button>
        </CardFooter>
      ) : null}
    </Card>
  );
}

function ArtifactResultIndex({
  artifacts,
  onOpen,
}: {
  readonly artifacts: readonly ResearchArtifactViewModel[];
  readonly onOpen: (artifactVersionId: DomainEntityId) => void;
}) {
  if (artifacts.length === 0) return null;
  return (
    <section className="artifact-index" aria-label="研究结果">
      <div className="artifact-index__heading">
        <h3>研究结果</h3>
        <span>{artifacts.length} 项</span>
      </div>
      <ul>
        {artifacts.map((artifact) => {
          const latestVersionId = artifact.latestVersionId;
          const registration = resolveArtifactRenderer(artifact.kind);
          return (
            <li key={artifact.id}>
              <div>
                <strong>{artifact.title}</strong>
                <span>
                  {latestVersionId === null
                    ? ARTIFACT_CARD_COPY.waiting
                    : ARTIFACT_CARD_COPY.generated}
                </span>
              </div>
              {latestVersionId !== null &&
              registration.capability === "supported" ? (
                <Button
                  variant="ghost"
                  size="small"
                  onClick={() => onOpen(latestVersionId)}
                >
                  查看报告
                </Button>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function useArtifactPresentation({
  runtime,
  projectId,
  runId,
  runCompleted,
}: ArtifactPresentationOptions): {
  readonly threadProjections: readonly ResearchThreadProjection[];
  readonly hasArtifacts: boolean;
  readonly artifactPanel: ReactNode;
  readonly artifactStatus: string;
  readonly fullscreenDialog: ReactNode;
} {
  const artifacts = useQuery({
    ...runtime.application.queries.artifactsByRun(
      projectId,
      runId ?? projectId,
    ),
    enabled: runId !== null,
  });
  const [selectedVersionId, setSelectedVersionId] =
    useState<DomainEntityId | null>(null);
  const [fullscreenVersionId, setFullscreenVersionId] =
    useState<DomainEntityId | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] =
    useState<DomainEntityId | null>(null);
  const [evidenceHistory, setEvidenceHistory] = useState<
    readonly DomainEntityId[]
  >([]);
  const selectEvidence = (evidenceId: DomainEntityId) => {
    setSelectedEvidenceId(evidenceId);
    setEvidenceHistory((current) =>
      current.at(-1) === evidenceId
        ? current
        : [...current, evidenceId].slice(-12),
    );
  };
  const goBackEvidence = () => {
    const previous = evidenceHistory.at(-2);
    if (!previous) return;
    setEvidenceHistory((current) => current.slice(0, -1));
    setSelectedEvidenceId(previous);
  };
  const artifactList = artifacts.data ?? [];
  const supportedVersionIds = artifactList.flatMap((artifact) => {
    const registration = resolveArtifactRenderer(artifact.kind);
    return registration.capability === "supported" &&
      artifact.latestVersionId !== null
      ? [artifact.latestVersionId]
      : [];
  });
  const activeVersionId =
    selectedVersionId !== null &&
    supportedVersionIds.includes(selectedVersionId)
      ? selectedVersionId
      : (supportedVersionIds[0] ?? null);
  const latestArtifactTimestamp = artifactList.reduce(
    (latest, artifact) =>
      Date.parse(artifact.createdAt) > Date.parse(latest)
        ? artifact.createdAt
        : latest,
    artifactList[0]?.createdAt ?? "",
  );
  const threadProjections =
    !runCompleted || artifactList.length === 0
      ? []
      : [
          {
            id: `artifact-results:${runId}`,
            occurredAt: latestArtifactTimestamp,
            node: (
              <ArtifactThreadCard
                runtime={runtime}
                projectId={projectId}
                artifacts={artifactList}
                onOpen={setFullscreenVersionId}
                onSelectEvidence={selectEvidence}
              />
            ),
          } satisfies ResearchThreadProjection,
        ];
  const artifactPanel = (
    <div className="artifact-overview">
      {artifacts.isPending ? (
        <Skeleton className="artifact-presentation__skeleton" />
      ) : null}
      {artifacts.isError ? (
        <ArtifactLoadError message={publicError(runtime, artifacts.error)} />
      ) : null}
      <ArtifactResultIndex
        artifacts={artifactList}
        onOpen={setSelectedVersionId}
      />
      {activeVersionId === null ? null : (
        <>
          <Separator />
          <ArtifactVersionBoundary
            runtime={runtime}
            projectId={projectId}
            artifactVersionId={activeVersionId}
            placement="docked"
            onOpenFullscreen={() => setFullscreenVersionId(activeVersionId)}
            onSelectEvidence={selectEvidence}
          />
        </>
      )}
    </div>
  );
  const fullscreenDialog = (
    <>
      {fullscreenVersionId === null ? null : (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setFullscreenVersionId(null);
          }}
        >
          <DialogContent className="paper-summary-dialog">
            <DialogHeader className="sr-only">
              <DialogTitle>研究产物报告</DialogTitle>
              <DialogDescription>
                当前选定 ArtifactVersion 的全屏研究报告
              </DialogDescription>
            </DialogHeader>
            <ArtifactVersionBoundary
              runtime={runtime}
              projectId={projectId}
              artifactVersionId={fullscreenVersionId}
              placement="fullscreen"
              onOpenFullscreen={null}
              onSelectEvidence={selectEvidence}
            />
          </DialogContent>
        </Dialog>
      )}
      <EvidenceInspector
        runtime={runtime}
        projectId={projectId}
        evidenceId={selectedEvidenceId}
        canGoBack={evidenceHistory.length > 1}
        onBack={goBackEvidence}
        onClose={() => setSelectedEvidenceId(null)}
      />
    </>
  );

  return {
    threadProjections,
    hasArtifacts: artifactList.length > 0,
    artifactPanel,
    artifactStatus: artifacts.isPending
      ? "载入中"
      : `${artifactList.length} 项`,
    fullscreenDialog,
  };
}
