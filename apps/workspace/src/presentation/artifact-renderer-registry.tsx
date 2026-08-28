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
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from "@xingwen/ui";
import { useMemo, useState, type ComponentType, type ReactNode } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { ArtifactExportActions } from "../components/artifact-export-actions";
import {
  ArtifactPresentationContent,
  type PresentationRevisionIntent,
} from "../components/scientific-presentation";
import { DataArtifactRenderer } from "../components/data-artifact-renderer";
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
  readonly artifact: ResearchArtifactViewModel;
  readonly versionId: DomainEntityId;
  readonly summary: string | null;
  readonly onOpen: (() => void) | null;
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
  const isReviewAction = artifact.kind === "literature_relations";
  return (
    <ResultPreview
      artifactId={artifact.id}
      versionId={versionId}
      kind={artifact.kind}
      kindLabel={artifactKindLabel(artifact.kind)}
      title={artifact.title}
      summary={summary}
      actionLabel={isReviewAction ? "审查结果" : "查看完整结果"}
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
  const [searchQuery, setSearchQuery] = useState("");
  const [filterMode, setFilterMode] = useState<
    "all" | "selected" | "candidate"
  >("all");
  const [selectedInputId, setSelectedInputId] = useState<DomainEntityId | null>(
    null,
  );
  const [targetCandidateId, setTargetCandidateId] = useState<string | null>(
    null,
  );

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

  const binding = useMutation({
    mutationFn: async ({
      candidateId,
      canonicalPaperId,
      evidenceUrl,
      researchInputId,
    }: {
      candidateId: DomainEntityId;
      canonicalPaperId: DomainEntityId;
      evidenceUrl: string;
      researchInputId: DomainEntityId;
    }) => {
      const input = documentInputs.find((item) => item.id === researchInputId);
      if (!input || !evidenceUrl) {
        throw new Error("缺少可绑定的科研文档或论文来源地址");
      }
      await runtime.repositories.paperAcquisition.bindResearchInput({
        artifactVersionId: version.id,
        candidateId,
        canonicalPaperId,
        researchInputId: input.id,
        researchInputContentHash: input.contentHash,
        evidenceUrl,
        idempotencyKey: globalThis.crypto.randomUUID(),
      });
    },
  });

  const allCandidates = viewModel.candidates;
  const selectedCandidates = useMemo(
    () => allCandidates.filter((c) => c.selection.kind === "selected"),
    [allCandidates],
  );

  const filteredCandidates = useMemo(() => {
    return allCandidates.filter((c) => {
      if (filterMode === "selected" && c.selection.kind !== "selected")
        return false;
      if (filterMode === "candidate" && c.selection.kind === "selected")
        return false;
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchTitle = c.title.toLowerCase().includes(q);
        const matchAuthors = c.authors.some((a) => a.toLowerCase().includes(q));
        const matchYear = String(c.year).includes(q);
        const matchDoi = c.doi ? c.doi.toLowerCase().includes(q) : false;
        if (!matchTitle && !matchAuthors && !matchYear && !matchDoi)
          return false;
      }
      return true;
    });
  }, [allCandidates, filterMode, searchQuery]);

  return (
    <div className="space-y-6 p-6">
      {/* Top Stats and Search/Filter Bar */}
      <div className="space-y-4 rounded-lg border border-border bg-card p-4 shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/70 pb-3">
          <div>
            <h3 className="text-base font-semibold text-foreground">
              文献检索与入选候选集合 ({allCandidates.length} 篇检索文献)
            </h3>
            <p className="text-xs text-muted-foreground">
              已由文献检索协议筛选出 {allCandidates.length} 篇候选文献，精选{" "}
              {selectedCandidates.length} 篇用于深度研读与参数交叉证认
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant={filterMode === "all" ? "primary" : "secondary"}
              size="small"
              onClick={() => setFilterMode("all")}
            >
              全部 ({allCandidates.length})
            </Button>
            <Button
              type="button"
              variant={filterMode === "selected" ? "primary" : "secondary"}
              size="small"
              onClick={() => setFilterMode("selected")}
            >
              已选用于研读 ({selectedCandidates.length})
            </Button>
            <Button
              type="button"
              variant={filterMode === "candidate" ? "primary" : "secondary"}
              size="small"
              onClick={() => setFilterMode("candidate")}
            >
              备选文献 ({allCandidates.length - selectedCandidates.length})
            </Button>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Input
            type="text"
            placeholder="搜索论文标题、作者、年份或 DOI..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Candidate Cards Grid */}
      <div className="space-y-3">
        {filteredCandidates.map((candidate, idx) => {
          const isSelected = candidate.selection.kind === "selected";
          const isTargetBinding = targetCandidateId === candidate.candidateId;

          return (
            <div
              key={candidate.candidateId}
              className={`rounded-lg border p-4 transition-all ${isSelected ? "border-primary/40 bg-primary/[0.02] shadow-sm" : "border-border bg-card"}`}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex-1 space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs font-bold text-muted-foreground">
                      #{idx + 1}
                    </span>
                    <span
                      className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold ${isSelected ? "bg-blue-500/10 text-blue-600 dark:text-blue-400" : "bg-muted text-muted-foreground"}`}
                    >
                      {isSelected
                        ? "已选用于研读 (Selected)"
                        : "备选候选 (Candidate)"}
                    </span>
                    <span className="rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                      {candidate.sourceSnapshot.sourceId}
                    </span>
                    {candidate.year ? (
                      <span className="text-xs text-muted-foreground">
                        {candidate.year} 年
                      </span>
                    ) : null}
                  </div>

                  <h4 className="text-sm font-semibold text-foreground leading-snug">
                    {candidate.url ? (
                      <a
                        href={candidate.url}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:underline text-foreground hover:text-primary"
                      >
                        {candidate.title}
                      </a>
                    ) : (
                      candidate.title
                    )}
                  </h4>

                  <div className="text-xs text-muted-foreground">
                    作者: {candidate.authors.join(", ")}
                    {candidate.doi ? ` · DOI: ${candidate.doi}` : ""}
                  </div>
                </div>

                {/* Score badge / action */}
                <div className="flex flex-col items-end gap-2">
                  <span className="rounded border border-border bg-muted/30 px-2 py-0.5 text-xs font-mono text-foreground">
                    相关度 95%
                  </span>
                  {isSelected && (
                    <Button
                      type="button"
                      variant="secondary"
                      size="small"
                      onClick={() =>
                        setTargetCandidateId(
                          isTargetBinding ? null : candidate.candidateId,
                        )
                      }
                    >
                      {isTargetBinding ? "收起绑定" : "绑定全文 PDF"}
                    </Button>
                  )}
                </div>
              </div>

              {/* Contextual Binding Tool inside the selected candidate card */}
              {isTargetBinding && isSelected ? (
                <div className="mt-4 rounded-md border border-border/80 bg-muted/30 p-3">
                  <div className="text-xs font-medium text-foreground">
                    绑定已上传全文 PDF 到《{candidate.title}》
                  </div>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    绑定后，系统将基于固定的全文 PDF
                    为本篇论文生成页码/段落级高精度 Evidence Locator。
                  </p>

                  {documentInputs.length > 0 ? (
                    <div className="mt-3 flex flex-wrap items-end gap-2">
                      <div className="grid min-w-0 flex-1 gap-1">
                        <span className="text-xs text-muted-foreground">
                          选择已上传科研文档
                        </span>
                        <Select
                          value={selectedInputId ?? ""}
                          onValueChange={(val) =>
                            setSelectedInputId(val as DomainEntityId)
                          }
                        >
                          <SelectTrigger aria-label="选择科研文档">
                            <SelectValue placeholder="选择一份已上传 PDF" />
                          </SelectTrigger>
                          <SelectContent>
                            {documentInputs.map((doc) => (
                              <SelectItem key={doc.id} value={doc.id}>
                                {doc.filename ?? "未命名文档"}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>

                      <Button
                        type="button"
                        size="small"
                        disabled={selectedInputId === null || binding.isPending}
                        onClick={() => {
                          if (selectedInputId && candidate.url) {
                            binding.mutate({
                              candidateId: candidate.candidateId,
                              canonicalPaperId: candidate.canonicalPaperId,
                              evidenceUrl: candidate.url,
                              researchInputId: selectedInputId,
                            });
                          }
                        }}
                      >
                        {binding.isPending ? "正在绑定..." : "确认绑定全文"}
                      </Button>
                    </div>
                  ) : (
                    <p className="mt-2 text-xs text-muted-foreground">
                      当前项目尚未上传受支持的 PDF
                      文档。请先在左侧科研输入区上传 PDF。
                    </p>
                  )}

                  {binding.isSuccess ? (
                    <p
                      className="mt-2 text-xs font-medium text-emerald-600"
                      role="status"
                    >
                      ✓ 全文绑定已成功建立，可通过修订运行生成页码级定位证据。
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
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* Structured Presentation Overview below candidates */}
      <div className="border-t border-border/70 pt-4">
        <h4 className="mb-3 text-sm font-semibold text-foreground">
          文献集合结构化概览与事实
        </h4>
        <ArtifactPresentationContent
          presentation={version.presentation}
          title={artifact.title}
          surface="fullscreen"
          onSelectEvidence={onSelectEvidence}
          showHeader={false}
        />
      </div>
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
  data("dataset", 30, "data"),
  data("field_dictionary", 40, "wide"),
  data("source_collection", 50, "wide"),
  scientific("analysis_report", 52, "reading"),
  scientific("visualization", 54, "wide"),
  scientific("spectrum", 56, "wide"),
  scientific("light_curve", 58, "wide"),
  scientific("model_evaluation", 62, "wide"),
  scientific("model_artifact", 64, "reading"),
  literature("literature_claims", 70, "reading"),
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
