import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import {
  ARTIFACT_KINDS,
  isArtifactKind,
  type ArtifactKind,
  type DataArtifactKind,
  type DomainEntityId,
  type PaperSummaryReview,
  type ScientificArtifactReview,
} from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  DataArtifactReviewViewModel,
  GraphArtifactReviewViewModel,
  LiteratureArtifactReviewViewModel,
  PaperAcquisitionReviewViewModel,
  ResearchArtifactViewModel,
} from "@xingwen/research-adapter";
import { Alert, AlertDescription, CardContent, Skeleton } from "@xingwen/ui";
import type { ComponentType, ReactNode } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { DataArtifactRenderer } from "../components/data-artifact-renderer";
import { ArtifactExportActions } from "../components/artifact-export-actions";
import { EvidenceLinks } from "../components/evidence-links";
import {
  PaperSummaryDetailRenderer,
  PaperSummaryThreadRenderer,
} from "../components/paper-summary-renderer";
import { ScientificArtifactRenderer } from "../components/scientific-artifact-renderer";
import { ScientificArtifactView } from "../components/scientific-artifact-view";
import {
  ARTIFACT_CARD_COPY,
  artifactKindDescription,
  artifactKindLabel,
} from "./artifact-presentation-labels";

export type ArtifactRendererSurface = "thread" | "docked" | "fullscreen";
export type ArtifactContentFamily =
  | "data"
  | "paper_summary"
  | "scientific"
  | "paper_collection"
  | "literature"
  | "graph";

export interface ArtifactRendererContentProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly placement: ArtifactRendererSurface;
  readonly onOpenFullscreen: (() => void) | null;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
}

interface LoadedRendererProps<ViewModel> extends ArtifactRendererContentProps {
  readonly viewModel: ViewModel;
}

interface TypedRendererDefinition<
  Kind extends ArtifactKind,
  ViewModel,
  QueryKey extends readonly unknown[],
> {
  readonly kind: Kind;
  readonly contentFamily: ArtifactContentFamily;
  readonly load: (
    props: ArtifactRendererContentProps & {
      readonly artifact: ResearchArtifactViewModel & { readonly kind: Kind };
    },
  ) => UseQueryOptions<ViewModel, Error, ViewModel, QueryKey>;
  readonly thread: (props: LoadedRendererProps<ViewModel>) => ReactNode;
  readonly detail: (props: LoadedRendererProps<ViewModel>) => ReactNode;
  readonly textFallback: (viewModel: ViewModel) => string;
  readonly evidenceIds: (viewModel: ViewModel) => readonly DomainEntityId[];
  readonly accepts?: (viewModel: ViewModel) => boolean;
}

export interface SupportedArtifactRendererRegistration {
  readonly kind: Exclude<ArtifactKind, "export">;
  readonly label: string;
  readonly capability: "supported";
  readonly contentFamily: ArtifactContentFamily;
  readonly surfaces: {
    readonly thread: true;
    readonly detail: true;
    readonly textFallback: true;
  };
  readonly Content: ComponentType<ArtifactRendererContentProps>;
  readonly TextFallback: ComponentType<ArtifactRendererContentProps>;
}

export interface UnsupportedArtifactRendererRegistration {
  readonly kind: "export";
  readonly label: string;
  readonly capability: "unsupported";
  readonly reason: string;
  readonly surfaces: {
    readonly thread: false;
    readonly detail: true;
    readonly textFallback: true;
  };
  readonly Content: ComponentType<ArtifactRendererContentProps>;
  readonly TextFallback: ComponentType<ArtifactRendererContentProps>;
}

export type ArtifactRendererRegistration =
  | SupportedArtifactRendererRegistration
  | UnsupportedArtifactRendererRegistration;

function PublicLoadError({
  runtime,
  error,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly error: unknown;
}) {
  return (
    <Alert variant="destructive">
      <AlertDescription>
        {runtime.researchAdapter.toPublicApplicationError(error).safeMessage}
      </AlertDescription>
    </Alert>
  );
}

function MetadataThreadFallback({
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

function defineRenderer<
  Kind extends Exclude<ArtifactKind, "export">,
  ViewModel,
  QueryKey extends readonly unknown[],
>(
  definition: TypedRendererDefinition<Kind, ViewModel, QueryKey>,
): SupportedArtifactRendererRegistration {
  type KindMatchedProps = ArtifactRendererContentProps & {
    readonly artifact: ResearchArtifactViewModel & { readonly kind: Kind };
  };

  function LoadedContent(props: KindMatchedProps) {
    const query = useQuery(
      definition.load({
        ...props,
        artifact: props.artifact,
      }),
    );
    if (query.isPending) {
      return (
        <div
          className="artifact-presentation__loading"
          aria-busy="true"
          aria-label={`正在读取${artifactKindLabel(definition.kind)}`}
        >
          <Skeleton className="artifact-presentation__skeleton" />
        </div>
      );
    }
    if (query.isError)
      return <PublicLoadError runtime={props.runtime} error={query.error} />;
    if (definition.accepts && !definition.accepts(query.data)) {
      return (
        <PublicLoadError
          runtime={props.runtime}
          error={
            new Error("Artifact read model does not match its registered kind")
          }
        />
      );
    }
    const loadedProps = { ...props, viewModel: query.data };
    const content =
      props.placement === "thread"
        ? definition.thread(loadedProps)
        : definition.detail(loadedProps);
    const evidenceIds = definition.evidenceIds(query.data);
    return (
      <>
        {content}
        {props.placement !== "thread" ? (
          <EvidenceLinks
            evidenceIds={evidenceIds}
            label={`${artifactKindLabel(definition.kind)}关联证据`}
            onSelectEvidence={props.onSelectEvidence}
          />
        ) : null}
      </>
    );
  }

  function Content(props: ArtifactRendererContentProps) {
    if (props.artifact.kind !== definition.kind) {
      return (
        <PublicLoadError
          runtime={props.runtime}
          error={new Error("Artifact renderer kind mismatch")}
        />
      );
    }
    return (
      <LoadedContent
        {...props}
        artifact={{ ...props.artifact, kind: definition.kind }}
      />
    );
  }

  function LoadedTextFallback(props: KindMatchedProps) {
    const query = useQuery(
      definition.load({
        ...props,
        artifact: props.artifact,
      }),
    );
    if (query.isPending) return <p aria-busy="true">正在读取文本替代内容。</p>;
    if (query.isError)
      return <PublicLoadError runtime={props.runtime} error={query.error} />;
    if (definition.accepts && !definition.accepts(query.data)) {
      return <p>Artifact read model does not match its registered kind.</p>;
    }
    return <p>{definition.textFallback(query.data)}</p>;
  }

  function TextFallback(props: ArtifactRendererContentProps) {
    if (props.artifact.kind !== definition.kind) {
      return <p>Artifact renderer kind mismatch.</p>;
    }
    return (
      <LoadedTextFallback
        {...props}
        artifact={{ ...props.artifact, kind: definition.kind }}
      />
    );
  }
  return {
    kind: definition.kind,
    label: artifactKindLabel(definition.kind),
    capability: "supported",
    contentFamily: definition.contentFamily,
    surfaces: { thread: true, detail: true, textFallback: true },
    Content,
    TextFallback,
  };
}

function data(kind: DataArtifactKind) {
  return defineRenderer({
    kind,
    contentFamily: "data",
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.dataArtifact(projectId, version.id, kind),
    thread: ({ viewModel, artifact, version, placement }) => (
      <DataArtifactRenderer
        review={viewModel}
        title={artifact.title}
        versionNumber={version.versionNumber}
        surface={placement}
      />
    ),
    detail: ({
      viewModel,
      artifact,
      version,
      placement,
      runtime,
      projectId,
    }) => (
      <>
        <ArtifactExportActions
          runtime={runtime}
          projectId={projectId}
          artifactVersionId={version.id}
          versionNumber={version.versionNumber}
          artifactKind={kind}
        />
        <DataArtifactRenderer
          review={viewModel}
          title={artifact.title}
          versionNumber={version.versionNumber}
          surface={placement}
        />
      </>
    ),
    textFallback: (viewModel: DataArtifactReviewViewModel) =>
      `${artifactKindLabel(kind)}，Schema ${viewModel.schemaVersion}，证据 ${viewModel.evidenceIds.length} 条。`,
    evidenceIds: (viewModel: DataArtifactReviewViewModel) =>
      viewModel.evidenceIds,
  });
}

type ScientificKind =
  | "analysis_report"
  | "visualization"
  | "spectrum"
  | "light_curve"
  | "model_evaluation"
  | "model_artifact";

function scientific(kind: ScientificKind) {
  return defineRenderer({
    kind,
    contentFamily: "scientific",
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.scientificArtifact(projectId, version.id),
    thread: ({ viewModel, artifact, version, placement, onSelectEvidence }) =>
      kind === "spectrum" || kind === "light_curve" ? (
        <ScientificArtifactRenderer
          review={viewModel}
          title={artifact.title}
          versionNumber={version.versionNumber}
          surface={placement}
          onSelectEvidence={onSelectEvidence}
        />
      ) : (
        <MetadataThreadFallback artifact={artifact} />
      ),
    detail: ({ viewModel, runtime, version, onSelectEvidence }) => (
      <ScientificArtifactView
        artifact={viewModel}
        loadContent={(contentHash) =>
          runtime.repositories.scientificArtifacts.getContent(
            version.id,
            contentHash,
          )
        }
        onSelectEvidence={onSelectEvidence}
      />
    ),
    textFallback: (viewModel: ScientificArtifactReview) =>
      `${viewModel.content.title}，版本 ${viewModel.versionNumber}，证据 ${viewModel.evidence.length} 条。`,
    evidenceIds: (viewModel: ScientificArtifactReview) =>
      viewModel.evidence.map((evidence) => evidence.id),
    accepts: (viewModel: ScientificArtifactReview) =>
      viewModel.content.kind === kind,
  });
}

const paperSummary = defineRenderer({
  kind: "paper_summary",
  contentFamily: "paper_summary",
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.paperSummary(projectId, version.id),
  thread: ({ viewModel, artifact, version, placement, onOpenFullscreen }) => (
    <PaperSummaryThreadRenderer
      artifact={artifact}
      version={version}
      review={viewModel}
      surface={placement}
      onOpenFullscreen={onOpenFullscreen}
      onReturnToOverview={null}
    />
  ),
  detail: ({ viewModel, artifact, version, placement, onOpenFullscreen }) => (
    <PaperSummaryDetailRenderer
      artifact={artifact}
      version={version}
      review={viewModel}
      surface={placement}
      onOpenFullscreen={onOpenFullscreen}
      onReturnToOverview={null}
    />
  ),
  textFallback: (viewModel: PaperSummaryReview) =>
    `${viewModel.paper.title}，包含 7 个摘要章节。`,
  evidenceIds: (viewModel: PaperSummaryReview) =>
    viewModel.evidence.map((item) => item.id),
});

const paperCollection = defineRenderer({
  kind: "paper_collection",
  contentFamily: "paper_collection",
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.paperAcquisition(projectId, version.id),
  thread: ({ viewModel, artifact, version, placement, onSelectEvidence }) => (
    <ScientificArtifactRenderer
      review={{ ...viewModel, kind: "paper_collection" }}
      title={artifact.title}
      versionNumber={version.versionNumber}
      surface={placement}
      onSelectEvidence={onSelectEvidence}
    />
  ),
  detail: ({ viewModel, artifact, version, placement, onSelectEvidence }) => (
    <ScientificArtifactRenderer
      review={{ ...viewModel, kind: "paper_collection" }}
      title={artifact.title}
      versionNumber={version.versionNumber}
      surface={placement}
      onSelectEvidence={onSelectEvidence}
    />
  ),
  textFallback: (viewModel: PaperAcquisitionReviewViewModel) =>
    `论文集合，候选 ${viewModel.candidates.length} 篇。`,
  evidenceIds: (viewModel: PaperAcquisitionReviewViewModel) =>
    viewModel.candidates.flatMap((candidate) =>
      candidate.evidence.map((evidence) => evidence.id),
    ),
});

type LiteratureKind =
  "literature_claims" | "literature_relations" | "reasoning_traces";

function literature(kind: LiteratureKind) {
  return defineRenderer({
    kind,
    contentFamily: "literature",
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.literatureArtifact(
        projectId,
        version.id,
        kind,
      ),
    thread: ({ viewModel, artifact, version, placement, onSelectEvidence }) => (
      <ScientificArtifactRenderer
        review={viewModel}
        title={artifact.title}
        versionNumber={version.versionNumber}
        surface={placement}
        onSelectEvidence={onSelectEvidence}
      />
    ),
    detail: ({ viewModel, artifact, version, placement, onSelectEvidence }) => (
      <ScientificArtifactRenderer
        review={viewModel}
        title={artifact.title}
        versionNumber={version.versionNumber}
        surface={placement}
        onSelectEvidence={onSelectEvidence}
      />
    ),
    textFallback: (viewModel: LiteratureArtifactReviewViewModel) =>
      `${artifactKindLabel(kind)}，版本 ${viewModel.versionNumber}。`,
    evidenceIds: (viewModel: LiteratureArtifactReviewViewModel) =>
      viewModel.evidenceIds,
  });
}

const graph = defineRenderer({
  kind: "graph",
  contentFamily: "graph",
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.graphArtifact(projectId, version.id),
  thread: ({ viewModel, artifact, version, placement, onSelectEvidence }) => (
    <ScientificArtifactRenderer
      review={viewModel}
      title={artifact.title}
      versionNumber={version.versionNumber}
      surface={placement}
      onSelectEvidence={onSelectEvidence}
    />
  ),
  detail: ({ viewModel, artifact, version, placement, onSelectEvidence }) => (
    <ScientificArtifactRenderer
      review={viewModel}
      title={artifact.title}
      versionNumber={version.versionNumber}
      surface={placement}
      onSelectEvidence={onSelectEvidence}
    />
  ),
  textFallback: (viewModel: GraphArtifactReviewViewModel) =>
    `证据图谱，${viewModel.nodeCount} 个节点，${viewModel.edgeCount} 条边。`,
  evidenceIds: () => [],
});

const exportUnsupported: UnsupportedArtifactRendererRegistration = {
  kind: "export",
  label: artifactKindLabel("export"),
  capability: "unsupported",
  reason:
    "当前契约只提供从 Dataset、Field Dictionary 与 Source Collection 固定版本生成导出；没有 Export Artifact 的专属读取契约。",
  surfaces: { thread: false, detail: true, textFallback: true },
  Content: ({ placement }) =>
    placement === "thread" ? null : (
      <Alert>
        <AlertDescription>
          当前 Export Artifact
          没有可验证的专属读取契约，请从数据产物详情生成固定版本导出。
        </AlertDescription>
      </Alert>
    ),
  TextFallback: () => <p>Export Artifact 暂无专属读取契约。</p>,
};

const ARTIFACT_RENDERER_REGISTRATIONS = [
  data("dataset"),
  data("field_dictionary"),
  data("source_collection"),
  scientific("analysis_report"),
  scientific("visualization"),
  scientific("spectrum"),
  scientific("light_curve"),
  scientific("model_evaluation"),
  scientific("model_artifact"),
  paperCollection,
  paperSummary,
  literature("literature_claims"),
  literature("literature_relations"),
  literature("reasoning_traces"),
  graph,
  exportUnsupported,
] satisfies readonly ArtifactRendererRegistration[];

export function createArtifactRendererRegistry(
  registrations: readonly ArtifactRendererRegistration[],
): ReadonlyMap<ArtifactKind, ArtifactRendererRegistration> {
  const registry = new Map<ArtifactKind, ArtifactRendererRegistration>();
  for (const registration of registrations) {
    if (!isArtifactKind(registration.kind))
      throw new Error(`Unknown Artifact kind: ${String(registration.kind)}`);
    if (registry.has(registration.kind))
      throw new Error(`Duplicate Artifact renderer: ${registration.kind}`);
    registry.set(registration.kind, registration);
  }
  const missing = ARTIFACT_KINDS.filter((kind) => !registry.has(kind));
  if (missing.length > 0)
    throw new Error(`Missing Artifact renderers: ${missing.join(", ")}`);
  return registry;
}

export const artifactRendererRegistry = createArtifactRendererRegistry(
  ARTIFACT_RENDERER_REGISTRATIONS,
);

export function resolveArtifactRenderer(
  kind: unknown,
): ArtifactRendererRegistration {
  if (!isArtifactKind(kind))
    throw new Error(`Unknown Artifact kind: ${String(kind)}`);
  const registration = artifactRendererRegistry.get(kind);
  if (!registration) throw new Error(`Missing Artifact renderer: ${kind}`);
  return registration;
}
