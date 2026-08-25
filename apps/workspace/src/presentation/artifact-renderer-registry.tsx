import {
  useMutation,
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
  Button,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@xingwen/ui";
import { ArrowRight } from "@xingwen/ui/icons";
import { useMemo, useState, type ComponentType, type ReactNode } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { ArtifactExportActions } from "../components/artifact-export-actions";
import { ArtifactPresentationContent } from "../components/scientific-presentation";
import { DataArtifactRenderer } from "../components/data-artifact-renderer";
import { PaperResultWorkspace } from "../components/paper-result-workspace";
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

export type ArtifactContentFamily =
  | "data"
  | "paper_summary"
  | "paper_collection"
  | "literature"
  | "graph"
  | "scientific";
export type ArtifactLayoutMode = "reading" | "wide" | "immersive";

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
  readonly artifact: ResearchArtifactViewModel;
  readonly versionId: DomainEntityId;
  readonly summary: string | null;
  readonly onOpen: (() => void) | null;
}

export interface ArtifactFullscreenRendererProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly version: ArtifactVersionMetadataViewModel;
  readonly onSelectEvidence: (evidenceId: DomainEntityId) => void;
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
    <Alert>
      <AlertDescription>
        <strong>{descriptor.unsupportedPresentation.title}</strong>
        <p>{descriptor.unsupportedPresentation.description}</p>
      </AlertDescription>
    </Alert>
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
  return (
    <div
      className="xw-result-block my-2 rounded-lg border border-border/70 bg-background p-4"
      data-testid={`artifact-result-${versionId}`}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="min-w-0">
            <h3 className="truncate text-sm font-medium text-foreground">
              {artifact.title}
            </h3>
            {summary ? (
              <p className="ui-text-label mt-1 line-clamp-2 text-muted-foreground">
                {summary}
              </p>
            ) : null}
          </div>
        </div>
        {onOpen ? (
          <Button
            size="small"
            variant="ghost"
            className="shrink-0 gap-1.5 text-xs"
            onClick={onOpen}
          >
            查看完整结果
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </div>
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
      queries: props.baselineVersion.provenance.evidenceIds.map((evidenceId) =>
        props.runtime.application.queries.evidence(props.projectId, evidenceId),
      ),
    });
    const currentEvidenceQueries = useQueries({
      queries: props.currentVersion.provenance.evidenceIds.map((evidenceId) =>
        props.runtime.application.queries.evidence(props.projectId, evidenceId),
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
    const baselineEvidence = baselineEvidenceQueries.flatMap((query) =>
      query.data ? [query.data] : [],
    );
    const currentEvidence = currentEvidenceQueries.flatMap((query) =>
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
    ThreadRenderer: ThreadResultBlock,
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

function data(kind: DataArtifactKind, displayPriority: number) {
  return defineRenderer({
    kind,
    contentFamily: "data",
    displayPriority,
    layoutMode: "wide",
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
      <div className="scientific-result-fullscreen space-y-4">
        <ArtifactExportActions
          runtime={runtime}
          projectId={projectId}
          artifactVersionId={version.id}
          artifactKind={kind}
          artifactTitle={artifact.title}
        />
        <ArtifactPresentationContent
          presentation={version.presentation}
          title={artifact.title}
          surface="fullscreen"
          onSelectEvidence={onSelectEvidence}
          showHeader={false}
        />
        <DataArtifactRenderer
          review={viewModel}
          title={artifact.title}
          surface="fullscreen"
          onSelectEvidence={(ids) => {
            const first = ids[0];
            if (first) onSelectEvidence(first);
          }}
          showSummary={false}
          enhancementOnly={kind === "dataset"}
        />
      </div>
    ),
    textFallback: (viewModel: DataArtifactReviewViewModel) =>
      `${artifactKindLabel(kind)}，证据 ${viewModel.evidenceIds.length} 条。`,
    buildDiffSnapshot: buildDataArtifactDiffSnapshot,
  });
}

function PaperSummaryFullscreen({
  runtime,
  projectId,
  artifact,
  version,
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
  buildDiffSnapshot: buildPaperSummaryDiffSnapshot,
});

function PaperCollectionFullscreen({
  runtime,
  projectId,
  artifact,
  version,
  viewModel,
  onSelectEvidence,
}: LoadedRendererProps<PaperAcquisitionReviewViewModel>) {
  const inputs = useQuery(
    runtime.application.queries.researchInputs(projectId),
  );
  const documentInputs = useMemo(
    () =>
      (inputs.data ?? []).filter(
        (input) =>
          input.type === "pdf" ||
          input.type === "image" ||
          input.mimeType === "application/pdf" ||
          ["image/jpeg", "image/png", "image/tiff", "image/webp"].includes(
            input.mimeType ?? "",
          ),
      ),
    [inputs.data],
  );
  const selectedCandidate = viewModel.candidates.find(
    (candidate) => candidate.selection.kind === "selected",
  );
  const [selectedInputId, setSelectedInputId] = useState<DomainEntityId | null>(
    null,
  );
  const binding = useMutation({
    mutationFn: async (researchInputId: DomainEntityId) => {
      const input = documentInputs.find((item) => item.id === researchInputId);
      if (!input || !selectedCandidate?.url) {
        throw new Error("缺少可绑定的科研文档或论文来源地址");
      }
      await runtime.repositories.paperAcquisition.bindResearchInput({
        artifactVersionId: version.id,
        candidateId: selectedCandidate.candidateId,
        canonicalPaperId: selectedCandidate.canonicalPaperId,
        researchInputId: input.id,
        researchInputContentHash: input.contentHash,
        evidenceUrl: selectedCandidate.url,
        idempotencyKey: globalThis.crypto.randomUUID(),
      });
    },
  });

  return (
    <div className="space-y-4 p-5">
      {selectedCandidate ? (
        <section className="rounded-md border border-border p-4">
          <h3 className="ui-text-heading font-medium">绑定已上传论文全文</h3>
          <p className="ui-text-label mt-1 text-muted-foreground">
            将一个已上传 PDF 或论文图像明确绑定到《{selectedCandidate.title}
            》，后续修订将基于固定全文版本生成可定位证据。
          </p>
          {documentInputs.length > 0 ? (
            <div className="mt-3 flex flex-wrap items-end gap-2">
              <label className="ui-text-label grid min-w-0 gap-1">
                已上传科研文档
                <Select
                  value={selectedInputId ?? ""}
                  onValueChange={(value) =>
                    setSelectedInputId(value as DomainEntityId)
                  }
                >
                  <SelectTrigger aria-label="选择已上传科研文档">
                    <SelectValue placeholder="选择一份科研文档" />
                  </SelectTrigger>
                  <SelectContent>
                    {documentInputs.map((input) => (
                      <SelectItem key={input.id} value={input.id}>
                        {input.filename ?? "未命名科研文档"}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              <Button
                type="button"
                size="small"
                disabled={selectedInputId === null || binding.isPending}
                onClick={() => {
                  if (selectedInputId) binding.mutate(selectedInputId);
                }}
              >
                {binding.isPending ? "正在绑定" : "绑定到所选论文"}
              </Button>
            </div>
          ) : (
            <p className="ui-text-label mt-3 text-muted-foreground">
              当前项目尚未上传受支持的科研文档。请先在研究输入区上传 PDF
              或论文图像。
            </p>
          )}
          {binding.isSuccess ? (
            <p className="ui-text-label mt-2 text-foreground" role="status">
              全文绑定已保存；可通过修订运行重新生成全文证据摘要。
            </p>
          ) : null}
          {binding.isError ? (
            <Alert className="mt-2" variant="destructive">
              <AlertDescription>
                {
                  runtime.researchAdapter.toPublicApplicationError(
                    binding.error,
                  ).safeMessage
                }
              </AlertDescription>
            </Alert>
          ) : null}
        </section>
      ) : null}
      <ArtifactPresentationContent
        presentation={version.presentation}
        title={artifact.title}
        surface="fullscreen"
        onSelectEvidence={onSelectEvidence}
        showHeader={false}
      />
    </div>
  );
}

const paperCollection = defineRenderer({
  kind: "paper_collection",
  contentFamily: "paper_collection",
  displayPriority: 20,
  layoutMode: "reading",
  capabilities: commonCapabilities,
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.paperAcquisition(projectId, version.id),
  fullscreen: (props) => <PaperCollectionFullscreen {...props} />,
  textFallback: (viewModel: PaperAcquisitionReviewViewModel) =>
    `论文集合，候选 ${viewModel.candidates.length} 篇。`,
  buildDiffSnapshot: buildPaperCollectionDiffSnapshot,
});

type LiteratureKind = "literature_claims" | "literature_relations";

function literature(kind: LiteratureKind, displayPriority: number) {
  return defineRenderer({
    kind,
    contentFamily: "literature",
    displayPriority,
    layoutMode: "wide",
    capabilities: commonCapabilities,
    load: ({ runtime, projectId, version }) =>
      runtime.application.queries.literatureArtifact(
        projectId,
        version.id,
        kind,
      ),
    fullscreen: ({ viewModel, artifact, version, onSelectEvidence }) => (
      <div className="scientific-result-fullscreen">
        <ScientificArtifactRenderer
          review={viewModel}
          presentation={version.presentation}
          title={artifact.title}
          surface="fullscreen"
          onSelectEvidence={onSelectEvidence}
        />
      </div>
    ),
    textFallback: () => `${artifactKindLabel(kind)}。`,
    buildDiffSnapshot: buildLiteratureDiffSnapshot,
  });
}

const graph = defineRenderer({
  kind: "graph",
  contentFamily: "graph",
  displayPriority: 60,
  layoutMode: "wide",
  capabilities: commonCapabilities,
  load: ({ runtime, projectId, version }) =>
    runtime.application.queries.graphArtifact(projectId, version.id),
  fullscreen: ({ viewModel, artifact, version, onSelectEvidence }) => (
    <div className="scientific-result-fullscreen">
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
    buildDiffSnapshot: buildScientificArtifactDiffSnapshot,
  });
}

const ARTIFACT_RENDERER_DESCRIPTORS = [
  paperSummary,
  paperCollection,
  data("dataset", 30),
  data("field_dictionary", 40),
  data("source_collection", 50),
  scientific("analysis_report", 52, "reading"),
  scientific("visualization", 54, "wide"),
  scientific("spectrum", 56, "wide"),
  scientific("light_curve", 58, "wide"),
  scientific("model_evaluation", 62, "wide"),
  scientific("model_artifact", 64, "reading"),
  literature("literature_claims", 70),
  literature("literature_relations", 80),
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
