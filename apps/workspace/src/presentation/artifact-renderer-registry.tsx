import {
  useQuery,
  useQueries,
  type UseQueryOptions,
} from "@tanstack/react-query";
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
  PaperAcquisitionReviewViewModel,
  ResearchArtifactViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Empty,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Skeleton,
} from "@xingwen/ui";
import { PackageCheck } from "@xingwen/ui/icons";
import type { ComponentType, ReactNode } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { ArtifactExportActions } from "../components/artifact-export-actions";
import type { PresentationRevisionIntent } from "../components/scientific-presentation";
import { DataArtifactRenderer } from "../components/data-artifact-renderer";
import { PaperCollectionWorkspace } from "../components/paper-collection-workspace";
import { PaperResultWorkspace } from "../components/paper-result-workspace";
import { PaperSummaryExportActions } from "../components/paper-summary-export-actions";
import { ScientificArtifactRenderer } from "../components/scientific-artifact-renderer";
import { ScientificDiffView } from "../components/scientific-diff-view";
import { artifactKindLabel } from "./artifact-presentation-labels";
import { workspaceQueryKeys } from "../application/query-keys";
import {
  buildDataArtifactDiffSnapshot,
  buildContractDiffItems,
  buildEvidenceDiffItems,
  buildGraphDiffSnapshot,
  buildLiteratureDiffSnapshot,
  buildPaperCollectionDiffSnapshot,
  buildPaperSummaryDiffSnapshot,
  buildScientificArtifactDiffSnapshot,
  buildSourceSetDiffItems,
  compareScientificSnapshots,
  type ArtifactReviewForDiff,
  type ScientificDiffSnapshot,
} from "./scientific-diff";

import { ResultPreview } from "../components/result-layout/result-preview";
import { ArtifactToolbar } from "../components/result-layout/artifact-toolbar";

export type ArtifactContentFamily =
  | "data"
  | "paper_summary"
  | "paper_collection"
  | "literature"
  | "graph"
  | "scientific";
export type ArtifactLayoutMode =
  "reading" | "wide" | "data" | "graph" | "immersive";

export interface ArtifactRendererCapabilities {
  readonly evidence: boolean;
  readonly download: boolean;
  readonly history: boolean;
  readonly revision: boolean;
  readonly pdf: boolean;
  readonly compare: boolean;
}

export interface ArtifactDiffRendererProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly baselineVersion: ArtifactVersionMetadataViewModel;
  readonly currentVersion: ArtifactVersionMetadataViewModel;
}

export interface ArtifactThreadRendererProps {
  readonly runtime?: WorkspaceRuntimeBoundaries;
  readonly projectId?: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly versionId: DomainEntityId;
  readonly summary: string | null;
  readonly onOpen: (() => void) | null;
}

export interface ArtifactSummaryRendererProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly versionId: DomainEntityId;
  readonly children: (summary: string | null) => ReactNode;
}

export type RevisionIntent = PresentationRevisionIntent;

export interface ArtifactFullscreenRendererProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
  readonly onRequestRevision?: (intent: RevisionIntent) => void;
  readonly paperPageRequest?: {
    readonly pageIndex: number;
    readonly nonce: number;
  } | null;
}

interface LoadedRendererProps<
  ViewModel,
> extends ArtifactFullscreenRendererProps {
  readonly viewModel: ViewModel;
}

interface TypedRendererDefinition<
  Kind extends ArtifactKind,
  ViewModel extends ArtifactReviewForDiff,
  QueryKey extends readonly unknown[],
> {
  readonly kind: Kind;
  readonly contentFamily: ArtifactContentFamily;
  readonly displayPriority: number;
  readonly layoutMode: ArtifactLayoutMode;
  readonly capabilities: ArtifactRendererCapabilities;
  readonly load: (
    props: ArtifactFullscreenRendererProps & {
      readonly artifact: ResearchArtifactViewModel & { readonly kind: Kind };
    },
  ) => UseQueryOptions<ViewModel, Error, ViewModel, QueryKey>;
  readonly fullscreen: (props: LoadedRendererProps<ViewModel>) => ReactNode;
  readonly textFallback: (viewModel: ViewModel) => string;
  readonly threadSummary?: (viewModel: ViewModel) => string | null;
  readonly buildDiffSnapshot: (viewModel: ViewModel) => ScientificDiffSnapshot;
  readonly accepts?: (viewModel: ViewModel) => boolean;
}

export interface ArtifactRendererDescriptor {
  readonly kind: ArtifactKind;
  readonly label: string;
  readonly capability: "supported" | "unsupported";
  readonly unsupportedPresentation: {
    readonly title: string;
    readonly description: string;
  } | null;
  readonly contentFamily: ArtifactContentFamily | "export" | "scientific";
  readonly displayPriority: number;
  readonly layoutMode: ArtifactLayoutMode;
  readonly capabilities: ArtifactRendererCapabilities;
  readonly ThreadRenderer: ComponentType<ArtifactThreadRendererProps>;
  readonly SummaryRenderer: ComponentType<ArtifactSummaryRendererProps>;
  readonly FullscreenRenderer: ComponentType<ArtifactFullscreenRendererProps>;
  readonly TextFallback: ComponentType<ArtifactFullscreenRendererProps>;
  readonly DiffRenderer: ComponentType<ArtifactDiffRendererProps>;
}

export function UnsupportedArtifactPresentation({
  descriptor,
}: {
  readonly descriptor: ArtifactRendererDescriptor;
}) {
  if (descriptor.unsupportedPresentation === null) return null;
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center px-6 py-10">
      <Empty className="min-h-72 w-full max-w-3xl">
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <PackageCheck aria-hidden="true" />
          </EmptyMedia>
          <EmptyTitle>{descriptor.unsupportedPresentation.title}</EmptyTitle>
          <EmptyDescription>
            {descriptor.unsupportedPresentation.description}
          </EmptyDescription>
        </EmptyHeader>
      </Empty>
    </div>
  );
}

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

function ThreadResultBlock({
  artifact,
  versionId,
  summary,
  onOpen,
}: ArtifactThreadRendererProps) {
  const isReviewAction = artifact.kind === "literature_relations";
  return (
    <ResultPreview
      artifactId={artifact.id}
      versionId={versionId}
      kind={artifact.kind}
      kindLabel={artifactKindLabel(artifact.kind)}
      title={artifact.title}
      summary={summary}
      actionLabel={isReviewAction ? "审查结果" : "打开"}
      onOpen={onOpen}
    />
  );
}

function defineRenderer<
  Kind extends Exclude<ArtifactKind, "export">,
  ViewModel extends ArtifactReviewForDiff,
  QueryKey extends readonly unknown[],
>(
  definition: TypedRendererDefinition<Kind, ViewModel, QueryKey>,
): ArtifactRendererDescriptor {
  type KindMatchedProps = ArtifactFullscreenRendererProps & {
    readonly artifact: ResearchArtifactViewModel & { readonly kind: Kind };
  };

  function LoadedFullscreen(props: KindMatchedProps) {
    const query = useQuery(definition.load(props));
    if (query.isPending) {
      return (
        <div className="p-6" aria-busy="true">
          <Skeleton className="h-32 w-full" />
        </div>
      );
    }
    if (query.isError) {
      return <PublicLoadError runtime={props.runtime} error={query.error} />;
    }
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
    return definition.fullscreen({ ...props, viewModel: query.data });
  }

  function FullscreenRenderer(props: ArtifactFullscreenRendererProps) {
    if (props.artifact.kind !== definition.kind) {
      return (
        <PublicLoadError
          runtime={props.runtime}
          error={new Error("Artifact renderer kind mismatch")}
        />
      );
    }
    return (
      <LoadedFullscreen
        {...props}
        artifact={{ ...props.artifact, kind: definition.kind }}
      />
    );
  }

  function LoadedSummary(
    props: ArtifactSummaryRendererProps & {
      readonly artifact: ResearchArtifactViewModel & { readonly kind: Kind };
      readonly version: ArtifactVersionMetadataViewModel;
    },
  ) {
    const query = useQuery(
      definition.load({
        runtime: props.runtime,
        projectId: props.projectId,
        artifact: props.artifact,
        version: props.version,
        onSelectEvidence: () => undefined,
      }),
    );
    if (!query.data) return props.children(null);
    return props.children(
      definition.threadSummary?.(query.data) ??
        definition.textFallback(query.data),
    );
  }

  function SummaryRenderer(props: ArtifactSummaryRendererProps) {
    const versionQuery = useQuery(
      props.runtime.application.queries.artifactVersion(
        props.projectId,
        props.versionId,
      ),
    );
    if (props.artifact.kind !== definition.kind || !versionQuery.data) {
      return props.children(null);
    }
    return (
      <LoadedSummary
        {...props}
        artifact={{ ...props.artifact, kind: definition.kind }}
        version={versionQuery.data}
      />
    );
  }

  function ThreadRenderer(props: ArtifactThreadRendererProps) {
    if (!props.runtime || !props.projectId) {
      return <ThreadResultBlock {...props} />;
    }
    return (
      <SummaryRenderer
        runtime={props.runtime}
        projectId={props.projectId}
        artifact={props.artifact}
        versionId={props.versionId}
      >
        {(summary) => (
          <ThreadResultBlock {...props} summary={summary ?? props.summary} />
        )}
      </SummaryRenderer>
    );
  }

  function LoadedTextFallback(props: KindMatchedProps) {
    const query = useQuery(definition.load(props));
    if (query.isPending) return <p aria-busy="true">正在读取文本替代内容。</p>;
    if (query.isError) {
      return <PublicLoadError runtime={props.runtime} error={query.error} />;
    }
    return <p>{definition.textFallback(query.data)}</p>;
  }

  function TextFallback(props: ArtifactFullscreenRendererProps) {
    if (props.artifact.kind !== definition.kind) {
      return <p>当前结果类型无法读取。</p>;
    }
    return (
      <LoadedTextFallback
        {...props}
        artifact={{ ...props.artifact, kind: definition.kind }}
      />
    );
  }

  function DiffRenderer(props: ArtifactDiffRendererProps) {
    if (props.artifact.kind !== definition.kind) {
      return <p>当前结果类型无法比较。</p>;
    }
    return (
      <LoadedDiff
        {...props}
        artifact={{ ...props.artifact, kind: definition.kind }}
      />
    );
  }

  function LoadedDiff(
    props: ArtifactDiffRendererProps & {
      readonly artifact: ResearchArtifactViewModel & { readonly kind: Kind };
    },
  ) {
    const baselineQuery = useQuery(
      definition.load({
        ...props,
        version: props.baselineVersion,
        onSelectEvidence: () => undefined,
      }),
    );
    const currentQuery = useQuery(
      definition.load({
        ...props,
        version: props.currentVersion,
        onSelectEvidence: () => undefined,
      }),
    );
    const baselineRunQuery = useQuery(
      props.runtime.application.queries.run(
        props.projectId,
        props.baselineVersion.createdByRunId,
      ),
    );
    const currentRunQuery = useQuery(
      props.runtime.application.queries.run(
        props.projectId,
        props.currentVersion.createdByRunId,
      ),
    );
    const baselineContractQuery = useQuery({
      ...props.runtime.application.queries.contract(
        props.projectId,
        baselineRunQuery.data?.contractId ??
          ("pending-contract" as DomainEntityId),
      ),
      enabled: baselineRunQuery.data !== undefined,
    });
    const currentContractQuery = useQuery({
      ...props.runtime.application.queries.contract(
        props.projectId,
        currentRunQuery.data?.contractId ??
          ("pending-contract" as DomainEntityId),
      ),
      enabled: currentRunQuery.data !== undefined,
    });
    const baselineEvidenceQueries = useQueries({
      queries: props.baselineVersion.evidence
        ? []
        : props.baselineVersion.provenance.evidenceIds.map((evidenceId) =>
            props.runtime.application.queries.evidence(
              props.projectId,
              evidenceId,
            ),
          ),
    });
    const currentEvidenceQueries = useQueries({
      queries: props.currentVersion.evidence
        ? []
        : props.currentVersion.provenance.evidenceIds.map((evidenceId) =>
            props.runtime.application.queries.evidence(
              props.projectId,
              evidenceId,
            ),
          ),
    });
    const baselineSourceQueries = useQueries({
      queries: props.baselineVersion.provenance.sourceSnapshotIds.map(
        (sourceSnapshotId) =>
          props.runtime.application.queries.sourceSnapshot(
            props.projectId,
            sourceSnapshotId,
          ),
      ),
    });
    const currentSourceQueries = useQueries({
      queries: props.currentVersion.provenance.sourceSnapshotIds.map(
        (sourceSnapshotId) =>
          props.runtime.application.queries.sourceSnapshot(
            props.projectId,
            sourceSnapshotId,
          ),
      ),
    });

    const relatedError = [
      baselineQuery,
      currentQuery,
      baselineRunQuery,
      currentRunQuery,
      baselineContractQuery,
      currentContractQuery,
      ...baselineEvidenceQueries,
      ...currentEvidenceQueries,
      ...baselineSourceQueries,
      ...currentSourceQueries,
    ].find((query) => query.isError)?.error;
    if (relatedError) {
      return <PublicLoadError runtime={props.runtime} error={relatedError} />;
    }

    if (
      baselineQuery.isPending ||
      currentQuery.isPending ||
      baselineRunQuery.isPending ||
      currentRunQuery.isPending ||
      baselineContractQuery.isPending ||
      currentContractQuery.isPending ||
      baselineEvidenceQueries.some((query) => query.isPending) ||
      currentEvidenceQueries.some((query) => query.isPending) ||
      baselineSourceQueries.some((query) => query.isPending) ||
      currentSourceQueries.some((query) => query.isPending)
    ) {
      return <p aria-busy="true">正在比较科学结果…</p>;
    }
    if (
      baselineQuery.data === undefined ||
      currentQuery.data === undefined ||
      baselineContractQuery.data === undefined ||
      currentContractQuery.data === undefined
    ) {
      return (
        <PublicLoadError
          runtime={props.runtime}
          error={new Error("Scientific Diff dependencies are unavailable")}
        />
      );
    }
    if (
      (definition.accepts && !definition.accepts(baselineQuery.data)) ||
      (definition.accepts && !definition.accepts(currentQuery.data))
    ) {
      return <p>所选结果无法安全比较。</p>;
    }

    const baselineSnapshot = definition.buildDiffSnapshot(baselineQuery.data);
    const currentSnapshot = definition.buildDiffSnapshot(currentQuery.data);
    const baselineEvidence =
      props.baselineVersion.evidence ??
      baselineEvidenceQueries.flatMap((query) =>
        query.data ? [query.data] : [],
      );
    const currentEvidence =
      props.currentVersion.evidence ??
      currentEvidenceQueries.flatMap((query) =>
        query.data ? [query.data] : [],
      );
    const baselineSources = baselineSourceQueries.flatMap((query) =>
      query.data ? [query.data] : [],
    );
    const currentSources = currentSourceQueries.flatMap((query) =>
      query.data ? [query.data] : [],
    );
    const baseline = {
      ...baselineSnapshot,
      contract: buildContractDiffItems(baselineContractQuery.data),
      sources: buildSourceSetDiffItems(baselineSources),
      evidence:
        baselineEvidence.length > 0
          ? buildEvidenceDiffItems(baselineEvidence)
          : baselineSnapshot.evidence,
    };
    const current = {
      ...currentSnapshot,
      contract: buildContractDiffItems(currentContractQuery.data),
      sources: buildSourceSetDiffItems(currentSources),
      evidence:
        currentEvidence.length > 0
          ? buildEvidenceDiffItems(currentEvidence)
          : currentSnapshot.evidence,
    };
    return (
      <ScientificDiffView
        results={compareScientificSnapshots(baseline, current)}
      />
    );
  }

  return {
    kind: definition.kind,
    label: artifactKindLabel(definition.kind),
    capability: "supported",
    unsupportedPresentation: null,
    contentFamily: definition.contentFamily,
    displayPriority: definition.displayPriority,
    layoutMode: definition.layoutMode,
    capabilities: definition.capabilities,
    ThreadRenderer,
    SummaryRenderer,
    FullscreenRenderer,
    TextFallback,
    DiffRenderer,
  };
}

const commonCapabilities: ArtifactRendererCapabilities = {
  evidence: true,
  download: false,
  history: true,
  revision: true,
  pdf: false,
  compare: true,
};

function data(
  kind: DataArtifactKind,
  displayPriority: number,
  layoutMode: ArtifactLayoutMode = "wide",
) {
  return defineRenderer({
    kind,
    contentFamily: "data",
    displayPriority,
    layoutMode,
    capabilities: { ...commonCapabilities, download: true },
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.dataArtifact(projectId, version.id, kind),
    fullscreen: ({
      viewModel,
      artifact,
      version,
      runtime,
      projectId,
      onSelectEvidence,
    }) => (
      <div className="scientific-result-fullscreen flex h-full min-h-0 flex-col gap-0">
        <ArtifactToolbar
          right={
            <ArtifactExportActions
              runtime={runtime}
              projectId={projectId}
              artifactVersionId={version.id}
              artifactKind={kind}
              artifactTitle={artifact.title}
            />
          }
        />
        <div className="min-h-0 flex-1 overflow-y-auto pt-4">
          <DataArtifactRenderer
            review={viewModel}
            title={artifact.title}
            surface="fullscreen"
            showSummary={false}
            onSelectEvidence={(ids) => {
              const first = ids[0];
              if (first) onSelectEvidence(first);
            }}
          />
        </div>
      </div>
    ),
    textFallback: (viewModel: DataArtifactReviewViewModel) =>
      `${artifactKindLabel(kind)}，证据 ${viewModel.evidenceIds.length} 条。`,
    threadSummary: (viewModel: DataArtifactReviewViewModel) => {
      if (viewModel.kind === "dataset") {
        return `${viewModel.rowCount} 行 · ${viewModel.fieldCount} 个字段 · ${viewModel.sourceSnapshots.length} 个来源`;
      }
      if (viewModel.kind === "field_dictionary") {
        return `${viewModel.fieldDefinitions.length} 个字段定义`;
      }
      return `${viewModel.members.length} 个来源 · ${viewModel.alignedRecordCount} 条对齐记录`;
    },
    buildDiffSnapshot: buildDataArtifactDiffSnapshot,
  });
}

function PaperSummaryFullscreen({
  runtime,
  projectId,
  artifact,
  version,
  viewModel,
  onSelectEvidence,
  paperPageRequest,
}: LoadedRendererProps<PaperSummaryReview>) {
  const documentSource = useQuery({
    ...runtime.application.queries.paperSummaryDocumentSource(
      projectId,
      version.id,
    ),
    retry: false,
  });
  const inputId = documentSource.data?.researchInputId ?? null;
  const documentUrl = inputId
    ? runtime.repositories.researchInputs.getContentUrl(inputId)
    : null;
  return (
    <PaperResultWorkspace
      artifact={artifact}
      version={version}
      onSelectEvidence={onSelectEvidence}
      documentUrl={documentUrl}
      documentKind={documentSource.data?.documentKind ?? null}
      requestedPage={paperPageRequest}
      paperMeta={{
        title: viewModel.paper.title,
        authors: viewModel.paper.authors,
        year: viewModel.paper.year,
      }}
      toolbar={
        <PaperSummaryExportActions
          runtime={runtime}
          artifactVersionId={version.id}
        />
      }
      className="h-full w-full"
    />
  );
}

const paperSummary = defineRenderer({
  kind: "paper_summary",
  contentFamily: "paper_summary",
  displayPriority: 10,
  layoutMode: "immersive",
  capabilities: { ...commonCapabilities, pdf: true },
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.paperSummary(projectId, version.id),
  fullscreen: (props) => <PaperSummaryFullscreen {...props} />,
  textFallback: (viewModel: PaperSummaryReview) =>
    `${viewModel.paper.title}，包含结构化论文摘要章节。`,
  threadSummary: (viewModel: PaperSummaryReview) => {
    const sections = [
      viewModel.background,
      viewModel.methodology,
      viewModel.dataset,
      viewModel.experiments,
      viewModel.discussion,
      viewModel.limitations,
    ].filter((section) => section.length > 0).length;
    return `${sections} 个章节 · 可对照原文`;
  },
  buildDiffSnapshot: buildPaperSummaryDiffSnapshot,
});

const paperCollection = defineRenderer({
  kind: "paper_collection",
  contentFamily: "paper_collection",
  displayPriority: 20,
  layoutMode: "wide",
  capabilities: commonCapabilities,
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.paperAcquisition(projectId, version.id),
  fullscreen: ({ runtime, projectId, version, viewModel }) => (
    <PaperCollectionWorkspace
      runtime={runtime}
      projectId={projectId}
      version={version}
      review={viewModel}
    />
  ),
  textFallback: (viewModel: PaperAcquisitionReviewViewModel) =>
    `论文集合，候选 ${viewModel.candidates.length} 篇。`,
  threadSummary: (viewModel: PaperAcquisitionReviewViewModel) =>
    `${viewModel.metrics.candidateCount} 篇候选 · ${viewModel.metrics.selectedCount} 篇已选`,
  buildDiffSnapshot: buildPaperCollectionDiffSnapshot,
});

type LiteratureKind = "literature_claims" | "literature_relations";

function literature(
  kind: LiteratureKind,
  displayPriority: number,
  layoutMode: ArtifactLayoutMode = "wide",
) {
  return defineRenderer({
    kind,
    contentFamily: "literature",
    displayPriority,
    layoutMode,
    capabilities: commonCapabilities,
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.literatureArtifact(
        projectId,
        version.id,
        kind,
      ),
    fullscreen: ({
      viewModel,
      artifact,
      version,
      onSelectEvidence,
      onRequestRevision,
    }) => (
      <div className="scientific-result-fullscreen">
        <ScientificArtifactRenderer
          review={viewModel}
          presentation={version.presentation}
          title={artifact.title}
          surface="fullscreen"
          onSelectEvidence={onSelectEvidence}
          onRequestRevision={onRequestRevision}
        />
      </div>
    ),
    textFallback: () => `${artifactKindLabel(kind)}。`,
    threadSummary: (viewModel) => {
      if (viewModel.kind === "literature_claims") {
        const accepted = viewModel.claims.filter(
          (claim) => claim.status === "accepted",
        ).length;
        return `${viewModel.claims.length} 条论断 · ${accepted} 条已接受`;
      }
      const candidates = viewModel.relations.filter(
        (relation) => relation.status === "candidate",
      ).length;
      return `${viewModel.relations.length} 条关系 · ${candidates} 条待审定`;
    },
    buildDiffSnapshot: buildLiteratureDiffSnapshot,
  });
}

const graph = defineRenderer({
  kind: "graph",
  contentFamily: "graph",
  displayPriority: 60,
  layoutMode: "graph",
  capabilities: commonCapabilities,
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.graphArtifact(projectId, version.id),
  fullscreen: ({ viewModel, artifact, version, onSelectEvidence }) => (
    <div className="scientific-result-fullscreen h-full">
      <ScientificArtifactRenderer
        review={viewModel}
        presentation={version.presentation}
        title={artifact.title}
        surface="fullscreen"
        onSelectEvidence={onSelectEvidence}
      />
    </div>
  ),
  textFallback: (viewModel: GraphArtifactReviewViewModel) =>
    `证据关系，${viewModel.nodeCount} 个节点，${viewModel.edgeCount} 条关系。`,
  threadSummary: (viewModel: GraphArtifactReviewViewModel) =>
    `${viewModel.nodeCount} 个节点 · ${viewModel.edgeCount} 条边`,
  buildDiffSnapshot: buildGraphDiffSnapshot,
});

const EXPORT_UNSUPPORTED_PRESENTATION = {
  title: "暂不支持预览此类结果",
  description: "请返回结构化数据结果下载已支持的格式。",
} as const;

const exportUnsupported: ArtifactRendererDescriptor = {
  kind: "export",
  label: artifactKindLabel("export"),
  capability: "unsupported",
  unsupportedPresentation: EXPORT_UNSUPPORTED_PRESENTATION,
  contentFamily: "export",
  displayPriority: 100,
  layoutMode: "reading",
  capabilities: {
    evidence: false,
    download: false,
    history: true,
    revision: false,
    pdf: false,
    compare: false,
  },
  ThreadRenderer: ThreadResultBlock,
  SummaryRenderer: ({ children }) => <>{children(null)}</>,
  FullscreenRenderer: () => (
    <UnsupportedArtifactPresentation descriptor={exportUnsupported} />
  ),
  TextFallback: () => <p>导出数据暂无专属读取契约。</p>,
  DiffRenderer: () => <p>导出数据不支持科学内容比较。</p>,
};

type ScientificKind =
  | "analysis_report"
  | "visualization"
  | "spectrum"
  | "light_curve"
  | "model_evaluation"
  | "model_artifact";

function scientificTextFallback(viewModel: ScientificArtifactReview): string {
  const content = viewModel.content;
  switch (content.kind) {
    case "analysis_report":
      return `${content.title}，证据 ${content.evidenceIds.length} 条。`;
    case "visualization":
      return `${content.title}，可视化说明：${content.description || "未提供"}。`;
    case "spectrum":
      return `${content.title}，采样 ${content.sampleCount} 点，检测谱线 ${content.detectedLines.length} 条。`;
    case "light_curve":
      return `${content.title}，采样 ${content.sampleCount} 点，最佳周期 ${content.bestPeriod} ${content.timeUnit}。`;
    case "model_evaluation":
      return `${content.title}，算法 ${content.algorithm}。`;
    case "model_artifact":
      return `${content.title}，ONNX 模型，算法 ${content.algorithm}。`;
  }
}

function scientificThreadSummary(viewModel: ScientificArtifactReview): string {
  const content = viewModel.content;
  switch (content.kind) {
    case "analysis_report":
      return `${content.findings.length} 项发现 · ${content.metrics.length} 项指标`;
    case "visualization":
      return content.description || "科学可视化";
    case "spectrum":
      return `${content.sampleCount} 个采样点 · ${content.detectedLines.length} 条检出谱线`;
    case "light_curve":
      return `${content.sampleCount} 个采样点 · 最佳周期 ${content.bestPeriod} ${content.timeUnit}`;
    case "model_evaluation": {
      const primaryMetrics = content.metrics
        .slice(0, 2)
        .map(
          (metric) =>
            `${metric.label} ${metric.value}${metric.unit ? ` ${metric.unit}` : ""}`,
        );
      return primaryMetrics.join(" · ") || content.algorithm;
    }
    case "model_artifact":
      return `${content.algorithm} ${content.algorithmVersion} · ONNX 模型`;
  }
}

function scientific(
  kind: ScientificKind,
  displayPriority: number,
  layoutMode: ArtifactLayoutMode,
) {
  return defineRenderer<
    ScientificKind,
    ScientificArtifactReview,
    ReturnType<typeof workspaceQueryKeys.scientificArtifact>
  >({
    kind,
    contentFamily: "scientific",
    displayPriority,
    layoutMode,
    capabilities: {
      ...commonCapabilities,
      download: kind === "model_artifact",
    },
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.scientificArtifact(
        projectId,
        version.id,
        kind,
      ),
    fullscreen: ({
      viewModel,
      artifact,
      runtime,
      version,
      onSelectEvidence,
    }) => (
      <div className="scientific-result-fullscreen">
        <ScientificArtifactRenderer
          review={viewModel}
          presentation={version.presentation}
          title={artifact.title}
          surface="fullscreen"
          onSelectEvidence={onSelectEvidence}
          loadContent={(contentHash) =>
            runtime.repositories.scientificArtifacts.getContent(
              version.id,
              contentHash,
            )
          }
        />
      </div>
    ),
    textFallback: scientificTextFallback,
    threadSummary: scientificThreadSummary,
    buildDiffSnapshot: buildScientificArtifactDiffSnapshot,
  });
}

const ARTIFACT_RENDERER_DESCRIPTORS = [
  paperSummary,
  paperCollection,
  data("dataset", 30, "data"),
  data("field_dictionary", 40, "wide"),
  data("source_collection", 50, "reading"),
  scientific("analysis_report", 52, "reading"),
  scientific("visualization", 54, "wide"),
  scientific("spectrum", 56, "wide"),
  scientific("light_curve", 58, "wide"),
  scientific("model_evaluation", 62, "wide"),
  scientific("model_artifact", 64, "wide"),
  literature("literature_claims", 70, "wide"),
  literature("literature_relations", 80, "wide"),
  graph,
  exportUnsupported,
] satisfies readonly ArtifactRendererDescriptor[];

export function createArtifactRendererRegistry(
  descriptors: readonly ArtifactRendererDescriptor[],
): ReadonlyMap<ArtifactKind, ArtifactRendererDescriptor> {
  const registry = new Map<ArtifactKind, ArtifactRendererDescriptor>();
  for (const descriptor of descriptors) {
    if (!isArtifactKind(descriptor.kind)) {
      throw new Error(`Unknown Artifact kind: ${String(descriptor.kind)}`);
    }
    if (registry.has(descriptor.kind)) {
      throw new Error(`Duplicate Artifact renderer: ${descriptor.kind}`);
    }
    registry.set(descriptor.kind, descriptor);
  }
  const missing = ARTIFACT_KINDS.filter((kind) => !registry.has(kind));
  if (missing.length > 0) {
    throw new Error(`Missing Artifact renderers: ${missing.join(", ")}`);
  }
  return registry;
}

export const artifactRendererRegistry = createArtifactRendererRegistry(
  ARTIFACT_RENDERER_DESCRIPTORS,
);

export function resolveArtifactRenderer(
  kind: unknown,
): ArtifactRendererDescriptor | null {
  return isArtifactKind(kind)
    ? (artifactRendererRegistry.get(kind) ?? null)
    : null;
}
