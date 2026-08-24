import { useMutation, useQuery } from "@tanstack/react-query";
import type {
  ArtifactVersionSummary,
  DomainEntityId,
  RevisionPlan,
} from "@xingwen/domain";
import type {
  ArtifactVersionMetadataViewModel,
  ResearchArtifactViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Button,
  Dialog,
  DialogClose,
  DialogContent,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
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
import { ArrowLeft, ChevronDown, Share2 } from "@xingwen/ui/icons";
import { useEffect, useRef, useState } from "react";

import type { WorkspaceRuntimeBoundaries } from "../boundaries";
import { artifactKindLabel } from "../presentation/artifact-presentation-labels";
import {
  resolveArtifactRenderer,
  type ArtifactRendererDescriptor,
} from "../presentation/artifact-renderer-registry";
import { ArtifactEvidenceSheet } from "./artifact-evidence-sheet";
import { ArtifactShareDialog } from "./artifact-share-dialog";
import { ArtifactSourceMode } from "./scientific-presentation";

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

function VersionSelector({
  versions,
  selectedVersionId,
  onSelect,
}: {
  readonly versions: readonly ArtifactVersionSummary[];
  readonly selectedVersionId: DomainEntityId;
  readonly onSelect: (versionId: DomainEntityId) => void;
}) {
  const ordered = [...versions].sort(
    (left, right) => right.versionNumber - left.versionNumber,
  );
  const selected =
    ordered.find((version) => version.id === selectedVersionId) ?? null;
  if (ordered.length === 0 || selected === null) return null;
  const isCurrent = ordered[0]?.id === selected.id;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="small"
          aria-haspopup="listbox"
          className="ui-text-label flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
          data-testid="artifact-version-selector"
        >
          <span>{isCurrent ? "当前结果" : "历史结果"}</span>
          <span>{versionTimestamp(selected.createdAt)}</span>
          <ChevronDown className="size-3.5" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-56">
        {ordered.map((version) => {
          const current = ordered[0]?.id === version.id;
          const active = version.id === selected.id;
          return (
            <DropdownMenuItem
              key={version.id}
              onClick={() => {
                if (!active) onSelect(version.id);
              }}
              className={active ? "font-medium" : undefined}
            >
              <span>{current ? "当前结果" : "历史结果"}</span>
              <span className="ui-text-label ml-auto pl-4 text-muted-foreground">
                {versionTimestamp(version.createdAt)}
              </span>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
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
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifact: ResearchArtifactViewModel;
  readonly currentVersion: ArtifactVersionMetadataViewModel;
  readonly versions: readonly ArtifactVersionSummary[];
  readonly descriptor: ArtifactRendererDescriptor;
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
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
  const DiffRenderer = descriptor.DiffRenderer;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="result-side-sheet">
        <SheetHeader>
          <SheetTitle>比较研究结果</SheetTitle>
          <SheetDescription>
            按科学含义查看结论、证据、关系、限制与冲突的变化。
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

function RevisionSheet({
  runtime,
  projectId,
  artifactId,
  artifactVersionId,
  versionNumber,
  parentRunRevision,
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
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly onRevisionStarted: () => void;
}) {
  const [requestedChange, setRequestedChange] = useState("");
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
    const feedback = await feedbackMutation.mutateAsync({
      projectId,
      artifactId,
      artifactVersionId,
      expectedVersionNumber: versionNumber,
      summary: change.slice(0, 200),
      requestedChange: change,
    });
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
          <SheetTitle>基于此结果重新分析</SheetTitle>
          <SheetDescription>
            新约束会形成修订计划；确认后创建派生研究，不修改当前结果或原研究。
          </SheetDescription>
        </SheetHeader>
        <div className="result-sheet-body">
          {plan === null ? (
            <>
              <label className="result-form-field">
                <span>希望调整什么？</span>
                <Textarea
                  value={requestedChange}
                  onChange={(event) => setRequestedChange(event.target.value)}
                  placeholder="例如：加入刚上传的新论文，并重新核对核心结论。"
                  maxLength={4000}
                />
              </label>
              <Button
                onClick={() => void createPlan()}
                disabled={
                  !requestedChange.trim() ||
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
  const [revisionOpen, setRevisionOpen] = useState(false);
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
        <header
          className="flex min-h-14 shrink-0 flex-wrap items-center gap-2 border-b border-border bg-background px-4 py-2"
          data-testid="artifact-fullscreen-header"
        >
          <div className="artifact-fullscreen-header__identity flex min-w-0 flex-wrap items-center gap-3">
            <DialogClose asChild>
              <Button
                variant="ghost"
                size="small"
                className="ui-text-label flex items-center gap-1.5 text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="size-4" aria-hidden="true" />
                <span>返回研究</span>
              </Button>
            </DialogClose>
            <div className="h-4 w-px bg-border" />
            <DialogTitle className="min-w-0 max-w-md truncate font-serif text-[length:var(--font-size-ui-heading)] font-semibold leading-[var(--line-height-ui-heading)] text-foreground">
              {artifact?.title ?? "研究结果"}
            </DialogTitle>
            {version ? (
              <ArtifactSourceMode sourceMode={version.sourceMode} />
            ) : null}
            {artifactId !== null && versions.length > 1 ? (
              <VersionSelector
                versions={versions}
                selectedVersionId={artifactVersionId}
                onSelect={(nextVersionId) =>
                  onOpenArtifactVersion?.(nextVersionId)
                }
              />
            ) : null}
          </div>
          <div className="artifact-fullscreen-header__actions flex flex-wrap items-center justify-end gap-2">
            {descriptor?.capabilities.evidence && evidenceIds.length > 0 ? (
              <Button
                size="small"
                variant="ghost"
                onClick={() => setSelectedEvidenceId(evidenceIds[0] ?? null)}
              >
                证据
              </Button>
            ) : null}
            {descriptor?.capabilities.compare && versions.length > 1 ? (
              <Button
                size="small"
                variant="ghost"
                onClick={() => setDiffOpen(true)}
              >
                比较结果
              </Button>
            ) : null}
            {descriptor?.capability === "supported" && artifact && version ? (
              <Button
                size="small"
                variant="ghost"
                onClick={() => setShareOpen(true)}
              >
                <Share2 className="size-4" aria-hidden="true" />
                分享
              </Button>
            ) : null}
            {descriptor?.capabilities.revision &&
            version &&
            parentRunQuery.data ? (
              <Button
                size="small"
                variant="ghost"
                onClick={() => setRevisionOpen(true)}
              >
                基于此结果重新分析
              </Button>
            ) : null}
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-hidden">
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
          {!isLoading && !error && artifact && version ? (
            FullscreenRenderer ? (
              <FullscreenRenderer
                key={version.id}
                runtime={runtime}
                projectId={projectId}
                artifact={artifact}
                version={version}
                onSelectEvidence={setSelectedEvidenceId}
                paperPageRequest={paperPageRequest}
              />
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
        {version && parentRunQuery.data ? (
          <RevisionSheet
            runtime={runtime}
            projectId={projectId}
            artifactId={version.artifactId}
            artifactVersionId={version.id}
            versionNumber={version.versionNumber}
            parentRunRevision={parentRunQuery.data.revision}
            open={revisionOpen}
            onOpenChange={setRevisionOpen}
            onRevisionStarted={onClose}
          />
        ) : null}
      </DialogContent>
    </Dialog>
  );
}
