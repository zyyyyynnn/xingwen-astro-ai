import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  ArtifactVersionSummary,
  DomainEntityId,
  PublicArtifactPresentation,
  RelationAdjudicationDecision,
  RevisionPlan,
} from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchArtifactViewModel,
  ResearchRunViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogContent,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  Skeleton,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Textarea,
} from "@xingwen/ui";
import { useEffect, useMemo, useRef, useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import type { CreateRevisionFeedbackVariables } from "../application/mutations";
import { artifactKindLabel } from "../presentation/artifact-presentation-labels";
import {
  resolveArtifactRenderer,
  type ArtifactRendererDescriptor,
  type RevisionIntent,
} from "../presentation/artifact-renderer-registry";
import { ArtifactEvidenceSheet } from "./artifact-evidence-sheet";
import { ArtifactShareDialog } from "./artifact-share-dialog";
import { ArtifactLayoutFrame, ArtifactWorkspaceHeader } from "./result-layout";

export interface ArtifactFullscreenWorkspaceProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly onClose: () => void;
  readonly onOpenArtifactVersion?:
    ((artifactVersionId: DomainEntityId) => void) | null;
}

function safeError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

function versionTimestamp(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleString(undefined, {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export function describeArtifactLineage(
  version: Pick<ArtifactVersionMetadataViewModel, "provenance">,
  run: Pick<ResearchRunViewModel, "parentRunId" | "derivationKind">,
  versions: readonly ArtifactVersionSummary[],
): {
  readonly description: string | null;
  readonly predecessor: ArtifactVersionSummary | null;
} {
  const predecessor =
    versions.find(
      (candidate) => candidate.id === version.provenance.supersedesVersionId,
    ) ?? null;
  const supersedesCopy = version.provenance.supersedesVersionId
    ? "此结果明确替代直接前序结果。"
    : null;
  const derivationCopy =
    run.parentRunId === null
      ? null
      : run.derivationKind === "revision"
        ? "本次研究是在前次研究基础上的修订。"
        : run.derivationKind === "retry"
          ? "本次研究是对前次研究的重新执行。"
          : run.derivationKind === "fork"
            ? "本次研究从前次研究分支派生。"
            : "本次研究沿用前次研究作为上游。";
  const description = [supersedesCopy, derivationCopy]
    .filter((value): value is string => value !== null)
    .join("");
  return { description: description || null, predecessor };
}

function ArtifactDiffSheet({
  runtime,
  projectId,
  artifact,
  currentVersion,
  versions,
  descriptor,
  open,
  onOpenChange,
  onOpenArtifactVersion,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly currentVersion: ArtifactVersionMetadataViewModel;
  readonly versions: readonly ArtifactVersionSummary[];
  readonly descriptor: ArtifactRendererDescriptor;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onOpenArtifactVersion:
    ((artifactVersionId: DomainEntityId) => void) | null;
}) {
  const candidates = [...versions]
    .filter((version) => version.id !== currentVersion.id)
    .sort((left, right) => right.versionNumber - left.versionNumber);
  const [baselineVersionId, setBaselineVersionId] =
    useState<DomainEntityId | null>(null);
  const effectiveBaselineVersionId = candidates.some(
    (version) => version.id === baselineVersionId,
  )
    ? baselineVersionId
    : (candidates[0]?.id ?? null);

  const baselineQuery = useQuery({
    ...runtime.application.queries.artifactVersion(
      projectId,
      effectiveBaselineVersionId as DomainEntityId,
    ),
    enabled: open && effectiveBaselineVersionId !== null,
  });
  const currentRunQuery = useQuery({
    ...runtime.application.queries.run(
      projectId,
      currentVersion.createdByRunId,
    ),
    enabled: open,
  });
  const DiffRenderer = descriptor.DiffRenderer;
  const lineage = currentRunQuery.data
    ? describeArtifactLineage(currentVersion, currentRunQuery.data, versions)
    : null;
  const predecessor = lineage?.predecessor ?? null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="result-side-sheet">
        <SheetHeader>
          <SheetTitle>比较研究结果</SheetTitle>
          <SheetDescription>
            查看研究契约、来源集合与科学内容的变化。
          </SheetDescription>
        </SheetHeader>
        <div className="result-sheet-body">
          <div className="scientific-diff-controls">
            <label>
              <span>作为比较基准的历史结果</span>
              <Select
                value={effectiveBaselineVersionId ?? undefined}
                onValueChange={(value) =>
                  setBaselineVersionId(value as DomainEntityId)
                }
              >
                <SelectTrigger aria-label="选择比较基准">
                  <SelectValue placeholder="选择历史结果" />
                </SelectTrigger>
                <SelectContent>
                  {candidates.map((candidate) => (
                    <SelectItem key={candidate.id} value={candidate.id}>
                      历史结果 · {versionTimestamp(candidate.createdAt)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </label>
            <p>当前结果 · {versionTimestamp(currentVersion.createdAt)}</p>
          </div>
          {currentRunQuery.isError ? (
            <Alert variant="destructive">
              <AlertDescription>
                {safeError(runtime, currentRunQuery.error)}
              </AlertDescription>
            </Alert>
          ) : lineage?.description ? (
            <section aria-label="结果沿革" className="scientific-diff-lineage">
              <h3>结果沿革</h3>
              <p>{lineage.description}</p>
              {predecessor && onOpenArtifactVersion ? (
                <Button
                  size="small"
                  variant="secondary"
                  onClick={() => {
                    onOpenChange(false);
                    onOpenArtifactVersion(predecessor.id);
                  }}
                >
                  打开直接前序结果
                </Button>
              ) : null}
            </section>
          ) : null}
          {baselineQuery.isPending ? (
            <p aria-busy="true">正在读取历史结果…</p>
          ) : baselineQuery.isError ? (
            <Alert variant="destructive">
              <AlertDescription>
                {safeError(runtime, baselineQuery.error)}
              </AlertDescription>
            </Alert>
          ) : baselineQuery.data ? (
            <DiffRenderer
              runtime={runtime}
              projectId={projectId}
              artifact={artifact}
              baselineVersion={baselineQuery.data}
              currentVersion={currentVersion}
            />
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function revisionImpact(plan: RevisionPlan): {
  readonly recompute: readonly string[];
  readonly reuse: readonly string[];
} {
  const labels = (decision: "recompute" | "reuse") => [
    ...new Set(
      plan.versionDecisions
        .filter((item) => item.decision === decision)
        .map((item) => artifactKindLabel(item.artifactKind)),
    ),
  ];
  return { recompute: labels("recompute"), reuse: labels("reuse") };
}

export type RevisionMode =
  | { readonly kind: "artifact_correction" }
  | { readonly kind: "relation_adjudication" }
  | {
      readonly kind: "relation_correction";
      readonly relationId: DomainEntityId;
    }
  | { readonly kind: "trace_correction"; readonly traceId: DomainEntityId };

export interface CandidateRelationOption {
  readonly relationId: DomainEntityId;
  readonly title: string;
}

export function toCandidateRelationOptions(
  presentation: PublicArtifactPresentation | null | undefined,
): CandidateRelationOption[] {
  if (!presentation || presentation.kind !== "literature_relations") {
    return [];
  }
  return presentation.entries
    .filter((entry) => entry.canAdjudicate === true)
    .map((entry) => ({
      relationId: entry.key as DomainEntityId,
      title: entry.title,
    }));
}

export function selectRevisionMode(
  candidateRelations: readonly CandidateRelationOption[],
): RevisionMode {
  return candidateRelations.length > 0
    ? { kind: "relation_adjudication" }
    : { kind: "artifact_correction" };
}

function revisionModeCopy(mode: RevisionMode): {
  readonly title: string;
  readonly description: string;
  readonly placeholder: string;
} {
  switch (mode.kind) {
    case "artifact_correction":
      return {
        title: "基于此结果重新分析",
        description:
          "新约束会形成修订计划；确认后创建派生研究，不修改当前结果或原研究。",
        placeholder: "例如：加入刚上传的新论文，并重新核对核心结论。",
      };
    case "relation_adjudication":
      return {
        title: "审定候选关系",
        description:
          "选择候选关系与审定结论，并说明审定理由；理由将作为该关系的审定依据进入证据链。",
        placeholder: "例如：该关系有明确证据支持，接受其进入证据图谱。",
      };
    case "relation_correction":
      return {
        title: "重新分析此关系",
        description:
          "说明希望如何重新分析这条关系；确认后创建派生研究，不修改当前结果或原研究。",
        placeholder: "例如：请重新核对此关系的证据与方向。",
      };
    case "trace_correction":
      return {
        title: "重新分析此推导",
        description:
          "说明希望如何重新分析这条推导；确认后创建派生研究，不修改当前结果或原研究。",
        placeholder: "例如：请重新检查此推导的关键步骤。",
      };
  }
}

function RevisionSheet({
  runtime,
  projectId,
  artifactId,
  artifactVersionId,
  versionNumber,
  parentRunRevision,
  mode,
  candidateRelations,
  open,
  onOpenChange,
  onRevisionStarted,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly versionNumber: number;
  readonly parentRunRevision: number;
  readonly mode: RevisionMode;
  readonly candidateRelations: readonly CandidateRelationOption[];
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onRevisionStarted: () => void;
}) {
  const copy = revisionModeCopy(mode);
  const [requestedChange, setRequestedChange] = useState("");
  const [selectedRelationId, setSelectedRelationId] =
    useState<DomainEntityId | null>(
      mode.kind === "relation_adjudication"
        ? (candidateRelations[0]?.relationId ?? null)
        : null,
    );
  const [selectedDecision, setSelectedDecision] =
    useState<RelationAdjudicationDecision>("accepted");
  const [plan, setPlan] = useState<RevisionPlan | null>(null);
  const feedbackMutation = useMutation(
    runtime.application.mutations.revisionFeedbackCreate(),
  );
  const planMutation = useMutation(
    runtime.application.mutations.revisionPlanCreate(),
  );
  const confirmMutation = useMutation(
    runtime.application.mutations.revisionPlanConfirm(),
  );

  const createPlan = async () => {
    const change = requestedChange.trim();
    if (!change) return;
    const base = {
      artifactId,
      artifactVersionId,
      expectedVersionNumber: versionNumber,
      summary: change.slice(0, 200),
      requestedChange: change,
    } as const;
    let variables: CreateRevisionFeedbackVariables;
    switch (mode.kind) {
      case "artifact_correction":
        variables = { ...base, kind: "artifact_correction" };
        break;
      case "relation_adjudication":
        if (selectedRelationId === null) return;
        variables = {
          ...base,
          kind: "relation_adjudication",
          relationId: selectedRelationId,
          decision: selectedDecision,
        };
        break;
      case "relation_correction":
        variables = {
          ...base,
          kind: "relation_correction",
          relationId: mode.relationId,
        };
        break;
      case "trace_correction":
        variables = {
          ...base,
          kind: "trace_correction",
          traceId: mode.traceId,
        };
        break;
      default: {
        const _exhaustive: never = mode;
        throw new Error(`Unsupported revision mode: ${String(_exhaustive)}`);
      }
    }
    const feedback = await feedbackMutation.mutateAsync(variables);
    const nextPlan = await planMutation.mutateAsync({
      projectId,
      feedbackId: feedback.id,
      expectedParentRunRevision: parentRunRevision,
    });
    setPlan(nextPlan);
  };

  const confirmPlan = async () => {
    if (!plan) return;
    await confirmMutation.mutateAsync({
      projectId,
      planId: plan.id,
      expectedPlanVersion: plan.version,
    });
    setPlan(null);
    setRequestedChange("");
    onOpenChange(false);
    onRevisionStarted();
  };

  const error =
    feedbackMutation.error ?? planMutation.error ?? confirmMutation.error;

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        onOpenChange(next);
        if (!next && !confirmMutation.isPending) setPlan(null);
      }}
    >
      <SheetContent side="right" className="result-side-sheet">
        <SheetHeader>
          <SheetTitle>{copy.title}</SheetTitle>
          <SheetDescription>{copy.description}</SheetDescription>
        </SheetHeader>
        <div className="result-sheet-body">
          {plan === null ? (
            <>
              {mode.kind === "relation_adjudication" ? (
                <>
                  <label className="result-form-field">
                    <span>选择候选关系</span>
                    <Select
                      value={selectedRelationId ?? undefined}
                      onValueChange={(value) =>
                        setSelectedRelationId(value as DomainEntityId)
                      }
                    >
                      <SelectTrigger aria-label="选择候选关系">
                        <SelectValue placeholder="选择候选关系" />
                      </SelectTrigger>
                      <SelectContent>
                        {candidateRelations.map((candidate) => (
                          <SelectItem
                            key={candidate.relationId}
                            value={candidate.relationId}
                          >
                            {candidate.title}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </label>
                  <label className="result-form-field">
                    <span>选择关系审定结论</span>
                    <Select
                      value={selectedDecision}
                      onValueChange={(value) =>
                        setSelectedDecision(
                          value as RelationAdjudicationDecision,
                        )
                      }
                    >
                      <SelectTrigger aria-label="选择关系审定结论">
                        <SelectValue placeholder="选择审定结论" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="accepted">接受并进入图谱</SelectItem>
                        <SelectItem value="rejected">
                          拒绝且不进入图谱
                        </SelectItem>
                      </SelectContent>
                    </Select>
                  </label>
                </>
              ) : null}
              <label className="result-form-field">
                <span>希望调整什么？</span>
                <Textarea
                  value={requestedChange}
                  onChange={(event) => setRequestedChange(event.target.value)}
                  placeholder={copy.placeholder}
                  maxLength={4000}
                />
              </label>
              <Button
                onClick={() => void createPlan()}
                disabled={
                  !requestedChange.trim() ||
                  (mode.kind === "relation_adjudication" &&
                    selectedRelationId === null) ||
                  feedbackMutation.isPending ||
                  planMutation.isPending
                }
              >
                生成修订计划
              </Button>
            </>
          ) : (
            <section className="revision-plan-impact">
              <div>
                <h3 className="font-medium">修订计划</h3>
                {revisionImpact(plan).recompute.length > 0 ? (
                  <p>
                    将重新生成：{revisionImpact(plan).recompute.join("、")}。
                  </p>
                ) : null}
                {revisionImpact(plan).reuse.length > 0 ? (
                  <p>保持不变：{revisionImpact(plan).reuse.join("、")}。</p>
                ) : null}
              </div>
              {plan.conflicts.length > 0 ? (
                <Alert variant="destructive">
                  <AlertDescription>
                    修订计划检测到冲突，暂时无法开始派生研究。请调整反馈内容后重试。
                  </AlertDescription>
                </Alert>
              ) : null}
              <Button
                onClick={() => void confirmPlan()}
                disabled={confirmMutation.isPending}
              >
                确认并创建派生研究
              </Button>
            </section>
          )}
          {error ? (
            <Alert variant="destructive">
              <AlertDescription>{safeError(runtime, error)}</AlertDescription>
            </Alert>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}

export function ArtifactFullscreenWorkspace({
  runtime,
  projectId,
  artifactVersionId,
  onClose,
  onOpenArtifactVersion = null,
}: ArtifactFullscreenWorkspaceProps) {
  const openerRef = useRef<HTMLElement | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] =
    useState<DomainEntityId | null>(null);
  const [revisionMode, setRevisionMode] = useState<RevisionMode | null>(null);
  const [revisionOpenNonce, setRevisionOpenNonce] = useState(0);
  const [diffOpen, setDiffOpen] = useState(false);
  const [shareOpen, setShareOpen] = useState(false);
  const [paperPageRequest, setPaperPageRequest] = useState<{
    readonly pageIndex: number;
    readonly nonce: number;
  } | null>(null);

  useEffect(
    () => () => {
      openerRef.current?.focus();
    },
    [],
  );

  const versionQuery = useQuery(
    runtime.application.queries.artifactVersion(projectId, artifactVersionId),
  );
  const artifactId = versionQuery.data?.artifactId ?? null;
  const artifactQuery = useQuery({
    ...runtime.application.queries.artifact(
      projectId,
      artifactId as DomainEntityId,
    ),
    enabled: artifactId !== null,
  });
  const versionsQuery = useQuery({
    ...runtime.application.queries.artifactVersions(
      projectId,
      artifactId as DomainEntityId,
    ),
    enabled: artifactId !== null,
  });

  const parentRunId = versionQuery.data?.createdByRunId ?? null;
  const parentRunQuery = useQuery({
    ...runtime.application.queries.run(
      projectId,
      parentRunId as DomainEntityId,
    ),
    enabled: parentRunId !== null,
  });
  const candidateRelations = useMemo<CandidateRelationOption[]>(
    () => toCandidateRelationOptions(versionQuery.data?.presentation),
    [versionQuery.data],
  );

  const openRevisionSheet = () => {
    setRevisionMode(selectRevisionMode(candidateRelations));
    setRevisionOpenNonce((nonce) => nonce + 1);
  };

  const handleObjectRevision = (intent: RevisionIntent) => {
    setRevisionMode(intent);
    setRevisionOpenNonce((nonce) => nonce + 1);
  };

  const isLoading =
    versionQuery.isPending || (artifactId !== null && artifactQuery.isPending);
  const error = versionQuery.error ?? artifactQuery.error;
  const version = versionQuery.data;
  const artifact = artifactQuery.data;
  const versions = versionsQuery.data ?? [];
  const descriptor = artifact ? resolveArtifactRenderer(artifact.kind) : null;
  const FullscreenRenderer = descriptor?.FullscreenRenderer ?? null;
  const evidenceIds = version?.provenance.evidenceIds ?? [];

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        aria-describedby={undefined}
        aria-modal="true"
        className="xw-artifact-fullscreen-workspace"
        data-testid="artifact-fullscreen-workspace"
        onOpenAutoFocus={() => {
          openerRef.current = document.activeElement as HTMLElement | null;
        }}
        showCloseButton={false}
      >
        <ArtifactWorkspaceHeader
          title={artifact?.title ?? "研究结果"}
          artifactVersionId={artifactVersionId}
          versions={versions}
          onSelectVersion={(nextVersionId) =>
            onOpenArtifactVersion?.(nextVersionId)
          }
          hasEvidence={Boolean(
            descriptor?.capabilities.evidence && evidenceIds.length > 0,
          )}
          onOpenEvidence={() => setSelectedEvidenceId(evidenceIds[0] ?? null)}
          canCompare={Boolean(
            descriptor?.capabilities.compare && versions.length > 1,
          )}
          onOpenCompare={() => setDiffOpen(true)}
          canShare={Boolean(
            descriptor?.capability === "supported" && artifact && version,
          )}
          onOpenShare={() => setShareOpen(true)}
          canRevise={Boolean(
            descriptor?.capabilities.revision && version && parentRunQuery.data,
          )}
          onOpenRevision={openRevisionSheet}
        />

        <main className="min-h-0 flex-1 overflow-hidden flex flex-col">
          {isLoading ? (
            <div className="flex h-full flex-col items-center justify-center p-8">
              <Skeleton className="mb-4 h-8 w-1/3" />
              <Skeleton className="h-64 w-2/3" />
              <p className="ui-text-body mt-4 text-muted-foreground">
                正在载入研究结果…
              </p>
            </div>
          ) : null}
          {error ? (
            <div className="p-8">
              <Alert variant="destructive">
                <AlertDescription>{safeError(runtime, error)}</AlertDescription>
              </Alert>
            </div>
          ) : null}
          {!isLoading && !error && artifact && version && descriptor ? (
            FullscreenRenderer ? (
              <ArtifactLayoutFrame mode={descriptor.layoutMode}>
                <FullscreenRenderer
                  key={version.id}
                  runtime={runtime}
                  projectId={projectId}
                  artifact={artifact}
                  version={version}
                  onSelectEvidence={setSelectedEvidenceId}
                  onRequestRevision={handleObjectRevision}
                  paperPageRequest={paperPageRequest}
                />
              </ArtifactLayoutFrame>
            ) : (
              <Alert className="m-6">
                <AlertDescription>当前结果类型暂时无法显示。</AlertDescription>
              </Alert>
            )
          ) : null}
        </main>

        <ArtifactEvidenceSheet
          runtime={runtime}
          projectId={projectId}
          evidenceId={selectedEvidenceId}
          open={selectedEvidenceId !== null}
          onOpenChange={(open) => {
            if (!open) setSelectedEvidenceId(null);
          }}
          onJumpToPaperPage={(pageIndex) =>
            setPaperPageRequest({ pageIndex, nonce: Date.now() })
          }
        />
        {artifact && version && descriptor ? (
          <ArtifactDiffSheet
            runtime={runtime}
            projectId={projectId}
            artifact={artifact}
            currentVersion={version}
            versions={versions}
            descriptor={descriptor}
            open={diffOpen}
            onOpenChange={setDiffOpen}
            onOpenArtifactVersion={onOpenArtifactVersion}
          />
        ) : null}
        {artifact && version ? (
          <ArtifactShareDialog
            runtime={runtime}
            projectId={projectId}
            artifactVersionId={version.id}
            artifactTitle={artifact.title}
            evidenceIds={evidenceIds}
            open={shareOpen}
            onOpenChange={setShareOpen}
          />
        ) : null}
        {artifact && version && parentRunQuery.data ? (
          <RevisionSheet
            key={revisionOpenNonce}
            runtime={runtime}
            projectId={projectId}
            artifactId={version.artifactId}
            artifactVersionId={version.id}
            versionNumber={version.versionNumber}
            parentRunRevision={parentRunQuery.data.revision}
            mode={revisionMode ?? { kind: "artifact_correction" }}
            candidateRelations={candidateRelations}
            open={revisionMode !== null}
            onOpenChange={(open) => {
              if (!open) setRevisionMode(null);
            }}
            onRevisionStarted={onClose}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
