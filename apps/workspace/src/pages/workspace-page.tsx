import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useRouteContext } from "@tanstack/react-router";
import type { RepositorySet } from "@xingwen/data-access";
import type { WorkspaceState } from "@xingwen/workspace-core";

import { ResearchShell } from "../components/research-shell";
import { useControllerState } from "../hooks/use-controller-state";
import { usePrivateSession } from "../hooks/use-private-session";

type EntityId = Parameters<RepositorySet["projects"]["getById"]>[0];
type Project = NonNullable<
  Awaited<ReturnType<RepositorySet["projects"]["getById"]>>
>;
type ResearchRun = NonNullable<
  Awaited<ReturnType<RepositorySet["runs"]["getById"]>>
>;
type Contract = NonNullable<
  Awaited<ReturnType<RepositorySet["contracts"]["getContractById"]>>
>;
type RunEvent = Awaited<
  ReturnType<RepositorySet["runs"]["recoverEvents"]>
>["events"][number];
type Artifact = Awaited<
  ReturnType<RepositorySet["artifacts"]["listByRun"]>
>[number];
type ArtifactVersion = NonNullable<
  Awaited<ReturnType<RepositorySet["artifacts"]["getVersion"]>>
>;
type Evidence = NonNullable<
  Awaited<ReturnType<RepositorySet["artifacts"]["getEvidence"]>>
>;
type Share = Awaited<ReturnType<RepositorySet["shares"]["list"]>>[number];
type CreateShareRequest = Parameters<RepositorySet["shares"]["create"]>[1];
type ShareFeedback = "unavailable" | "network" | null;

interface WorkspaceData {
  readonly project: Project;
  readonly contract: Contract | null;
  readonly runs: readonly ResearchRun[];
  readonly run: ResearchRun | null;
  readonly events: readonly RunEvent[];
  readonly artifacts: readonly Artifact[];
  readonly selectedArtifact: Artifact | null;
  readonly selectedVersion: ArtifactVersion | null;
  readonly selectedEvidence: Evidence | null;
  readonly shares: readonly Share[];
}

type LoadState =
  | { readonly status: "loading" }
  | { readonly status: "empty" }
  | { readonly status: "error" }
  | { readonly status: "ready"; readonly data: WorkspaceData };

export interface WorkspacePageProps {
  readonly projectId?: string;
  readonly draftId?: string;
  readonly contractId?: string;
  readonly runId?: string;
}

function toEntityId(value: string | undefined): EntityId | null {
  return value && value.trim() ? (value as EntityId) : null;
}

function workspaceStatus(state: WorkspaceState): string {
  switch (state.status) {
    case "idle":
      return "尚未载入";
    case "loading":
      return "正在恢复工作区";
    case "ready":
      return `已保存 revision ${state.snapshot.revision}`;
    case "draft":
      return state.snapshot
        ? "本地更改尚未保存"
        : "未保存本地草稿（revision 0）";
    case "saving":
      return "正在保存工作区";
    case "conflict":
      return "检测到版本冲突";
    case "error":
      return state.dirty ? "保存失败，本地更改仍保留" : "无法恢复工作区";
  }
}

function evidenceSummary(evidence: Evidence): string {
  if (evidence.locator?.kind === "database_cell") {
    return `数据库字段 ${evidence.locator.field}`;
  }
  if (evidence.locator?.kind === "paper_text") {
    return `论文 ${evidence.locator.section}`;
  }
  if (evidence.locator?.kind === "reasoning_trace") {
    return `推理步骤 ${evidence.locator.stepKey}`;
  }
  if (evidence.locator?.kind === "model_extraction") {
    return `提取 ${evidence.locator.promptName}`;
  }
  return "无 locator";
}

function isUnavailableShareError(error: unknown): boolean {
  return error instanceof Error && error.name === "NotFoundError";
}

function draftFromWorkspaceState(state: WorkspaceState) {
  if (
    state.status === "ready" ||
    state.status === "draft" ||
    state.status === "saving" ||
    state.status === "error"
  ) {
    return state.draft;
  }
  return null;
}

function preservesLocalWorkspaceState(state: WorkspaceState): boolean {
  return (
    state.status === "saving" ||
    state.status === "conflict" ||
    ((state.status === "draft" || state.status === "error") && state.dirty)
  );
}

export function WorkspacePage({
  projectId: projectIdProp,
  draftId: draftIdProp,
  contractId: contractIdProp,
  runId: runIdProp,
}: WorkspacePageProps) {
  const runtime = useRouteContext({ from: "/workspace" });
  const sessionState = usePrivateSession(runtime);
  const controllerState = useControllerState(runtime.workspaceController);
  const fixtureContext =
    runtime.adapterKind === "fixture" ? runtime.bootstrap : null;
  const projectId =
    toEntityId(projectIdProp) ?? fixtureContext?.projectId ?? null;
  const draftId = toEntityId(draftIdProp) ?? fixtureContext?.draftId ?? null;
  const contractId =
    toEntityId(contractIdProp) ?? fixtureContext?.contractId ?? null;
  const explicitRunId = toEntityId(runIdProp);
  const routeRunId = explicitRunId ?? fixtureContext?.runId ?? null;
  const [loadState, setLoadState] = useState<LoadState>({ status: "loading" });
  const [selectedRunId, setSelectedRunId] = useState<EntityId | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareFeedback, setShareFeedback] = useState<ShareFeedback>(null);
  const [sharePending, setSharePending] = useState(false);
  const [selectionError, setSelectionError] = useState(false);
  const [eventRecoveryError, setEventRecoveryError] = useState(false);
  const [eventRecoveryPending, setEventRecoveryPending] = useState(false);
  const loadSequence = useRef(0);
  const selectionSequence = useRef(0);
  const recoverySequence = useRef(0);
  const shareRequestPending = useRef(false);

  const loadWorkspace = useCallback(async () => {
    const request = ++loadSequence.current;
    const isCurrent = () => request === loadSequence.current;
    if (sessionState.status !== "ready") return;
    if (!projectId) {
      if (isCurrent()) setLoadState({ status: "empty" });
      return;
    }

    setLoadState({ status: "loading" });
    try {
      if (
        !preservesLocalWorkspaceState(runtime.workspaceController.getState())
      ) {
        await runtime.workspaceController.load(projectId);
      }
      if (!isCurrent()) return;
      const project = await runtime.repositories.projects.getById(projectId);
      if (!isCurrent()) return;
      if (!project) {
        setLoadState({ status: "empty" });
        return;
      }
      const workspaceDraft = draftFromWorkspaceState(
        runtime.workspaceController.getState(),
      );
      const preferredRunId =
        selectedRunId ??
        explicitRunId ??
        workspaceDraft?.activeRunId ??
        routeRunId ??
        project.latestRunId;
      const candidateRunIds = [
        preferredRunId,
        routeRunId,
        workspaceDraft?.activeRunId ?? null,
        project.latestRunId,
      ].filter((candidate): candidate is EntityId => candidate !== null);
      const runs = (
        await Promise.all(
          [...new Set(candidateRunIds)].map((id) =>
            runtime.repositories.runs.getById(id),
          ),
        )
      ).filter((candidate): candidate is ResearchRun => candidate !== null);
      const run = preferredRunId
        ? (runs.find((candidate) => candidate.id === preferredRunId) ?? null)
        : null;
      if (!isCurrent()) return;
      const resolvedContractId =
        contractId ?? run?.contractId ?? project.activeContractId;
      const contract = resolvedContractId
        ? await runtime.repositories.contracts.getContractById(
            resolvedContractId,
          )
        : null;
      if (!isCurrent()) return;
      const recovery = run
        ? await runtime.repositories.runs.recoverEvents(run.id)
        : { events: [], nextCursor: null, latestSequence: 0 };
      if (!isCurrent()) return;
      const artifacts = run
        ? await runtime.repositories.artifacts.listByRun(run.id)
        : [];
      if (!isCurrent()) return;
      const selectedSlot =
        workspaceDraft?.panelSlots.find(
          (slot) =>
            slot.slotId === "primary" && slot.artifactVersionId !== null,
        ) ??
        workspaceDraft?.panelSlots.find(
          (slot) => slot.artifactVersionId !== null,
        ) ??
        null;
      const selectedVersionId =
        selectedSlot?.artifactVersionId ??
        artifacts[0]?.latestVersionId ??
        null;
      const selectedVersion = selectedVersionId
        ? await runtime.repositories.artifacts.getVersion(selectedVersionId)
        : null;
      if (!isCurrent()) return;
      const selectedArtifact = selectedVersion
        ? (artifacts.find(
            (artifact) => artifact.id === selectedVersion.artifactId,
          ) ?? null)
        : (artifacts[0] ?? null);
      const selectedEvidenceId =
        selectedSlot?.evidenceId ??
        workspaceDraft?.pinnedEvidenceIds[0] ??
        selectedVersion?.evidenceIds[0] ??
        null;
      const selectedEvidence = selectedEvidenceId
        ? await runtime.repositories.artifacts.getEvidence(selectedEvidenceId)
        : null;
      if (!isCurrent()) return;
      const shares = await runtime.repositories.shares.list(project.id);
      if (!isCurrent()) return;
      setLoadState({
        status: "ready",
        data: {
          project,
          contract,
          runs,
          run,
          events: recovery.events,
          artifacts,
          selectedArtifact,
          selectedVersion,
          selectedEvidence,
          shares,
        },
      });
    } catch {
      if (isCurrent()) setLoadState({ status: "error" });
    }
  }, [
    contractId,
    explicitRunId,
    projectId,
    routeRunId,
    runtime.repositories,
    runtime.workspaceController,
    selectedRunId,
    sessionState.status,
  ]);

  useEffect(() => {
    void Promise.resolve().then(loadWorkspace);
  }, [loadWorkspace]);

  const data = loadState.status === "ready" ? loadState.data : null;

  const selectRun = async (run: ResearchRun) => {
    const selection = ++selectionSequence.current;
    try {
      await runtime.workspaceController.setActiveRun(run.id);
      if (selection !== selectionSequence.current) return;
      setSelectedRunId(run.id);
      setSelectionError(false);
    } catch {
      if (selection === selectionSequence.current) setSelectionError(true);
    }
  };

  const selectArtifact = async (artifact: Artifact) => {
    const selection = ++selectionSequence.current;
    try {
      const version = artifact.latestVersionId
        ? await runtime.repositories.artifacts.getVersion(
            artifact.latestVersionId,
          )
        : null;
      if (selection !== selectionSequence.current) return;
      const evidence = version?.evidenceIds[0]
        ? await runtime.repositories.artifacts.getEvidence(
            version.evidenceIds[0],
          )
        : null;
      if (selection !== selectionSequence.current) return;
      if (version) {
        await runtime.workspaceController.setPanelSlot({
          slotId: "primary",
          panelType: "observatory",
          artifactVersionId: version.id,
          evidenceId: evidence?.id ?? null,
        });
        if (selection !== selectionSequence.current) return;
      }
      setLoadState((current) =>
        current.status === "ready"
          ? {
              status: "ready",
              data: {
                ...current.data,
                selectedArtifact: artifact,
                selectedVersion: version,
                selectedEvidence: evidence,
              },
            }
          : current,
      );
      setSelectionError(false);
    } catch {
      if (selection === selectionSequence.current) setSelectionError(true);
    }
  };

  const selectEvidence = async (evidence: Evidence) => {
    const selection = ++selectionSequence.current;
    try {
      if (!data?.selectedVersion) return;
      await runtime.workspaceController.setPanelSlot({
        slotId: "primary",
        panelType: "observatory",
        artifactVersionId: data.selectedVersion.id,
        evidenceId: evidence.id,
      });
      if (selection !== selectionSequence.current) return;
      await runtime.workspaceController.pinEvidence(evidence.id);
      if (selection !== selectionSequence.current) return;
      setLoadState((current) =>
        current.status === "ready"
          ? {
              status: "ready",
              data: { ...current.data, selectedEvidence: evidence },
            }
          : current,
      );
      setSelectionError(false);
    } catch {
      if (selection === selectionSequence.current) setSelectionError(true);
    }
  };

  const recoverRunEvents = async () => {
    if (!data?.run || eventRecoveryPending) return;
    const request = ++recoverySequence.current;
    setEventRecoveryPending(true);
    setEventRecoveryError(false);
    try {
      const recovery = await runtime.repositories.runs.recoverEvents(
        data.run.id,
      );
      if (request !== recoverySequence.current) return;
      setLoadState((current) =>
        current.status === "ready" && current.data.run?.id === data.run?.id
          ? {
              status: "ready",
              data: { ...current.data, events: recovery.events },
            }
          : current,
      );
    } catch {
      if (request === recoverySequence.current) setEventRecoveryError(true);
    } finally {
      if (request === recoverySequence.current) setEventRecoveryPending(false);
    }
  };

  const createShare = async () => {
    if (
      !data?.selectedVersion ||
      !data.selectedEvidence ||
      shareRequestPending.current
    ) {
      return;
    }
    shareRequestPending.current = true;
    setSharePending(true);
    const request: CreateShareRequest = {
      title:
        `${data.selectedArtifact?.title ?? "Research artifact"} v${data.selectedVersion.versionNumber}` as CreateShareRequest["title"],
      artifactVersionIds: [data.selectedVersion.id],
      evidenceIds: [data.selectedEvidence.id],
      expiresAt: new Date(
        Date.now() + 7 * 24 * 60 * 60 * 1000,
      ).toISOString() as CreateShareRequest["expiresAt"],
      redactionPolicy: "public_metadata_only",
    };
    try {
      const created = await runtime.repositories.shares.create(
        data.project.id,
        request,
      );
      const metadata: Share = {
        id: created.id,
        projectId: created.projectId,
        title: created.title,
        status: created.status,
        redactionPolicy: created.redactionPolicy,
        artifactVersionIds: created.artifactVersionIds,
        evidenceIds: created.evidenceIds,
        createdAt: created.createdAt,
        expiresAt: created.expiresAt,
        revokedAt: created.revokedAt,
      };
      setShareUrl(`/share/${created.shareToken}`);
      setShareFeedback(null);
      setLoadState((current) =>
        current.status === "ready"
          ? {
              status: "ready",
              data: {
                ...current.data,
                shares: [...current.data.shares, metadata],
              },
            }
          : current,
      );
    } catch (error) {
      setShareFeedback(
        isUnavailableShareError(error) ? "unavailable" : "network",
      );
    } finally {
      shareRequestPending.current = false;
      setSharePending(false);
    }
  };

  const revokeShare = async (share: Share) => {
    if (!data) return;
    try {
      await runtime.repositories.shares.revoke(data.project.id, share.id);
      setLoadState((current) =>
        current.status === "ready"
          ? {
              status: "ready",
              data: {
                ...current.data,
                shares: current.data.shares.map((item) =>
                  item.id === share.id
                    ? { ...item, status: "revoked", revokedAt: item.revokedAt }
                    : item,
                ),
              },
            }
          : current,
      );
      setShareFeedback(null);
    } catch (error) {
      setShareFeedback(
        isUnavailableShareError(error) ? "unavailable" : "network",
      );
    }
  };

  const sessionLabel =
    sessionState.status === "loading"
      ? "正在建立会话"
      : sessionState.status === "error"
        ? "会话不可用"
        : sessionState.status === "expired"
          ? "会话已过期"
          : runtime.adapterKind === "fixture"
            ? "Fixture / Demo Replay"
            : "HTTP 适配器";
  const railStatus = data ? (
    <>
      <span>Project: {data.project.name}</span>
      <span>Run: {data.run?.id ?? "未选择"}</span>
      <span>
        Adapter: {runtime.adapterKind === "fixture" ? "Fixture" : "HTTP"}
      </span>
      <span>Execution: {data.run?.executionMode ?? "未选择"}</span>
      <span>Source: {data.selectedVersion?.sourceMode ?? "未选择"}</span>
      <span>Status: {data.run?.status ?? "未选择"}</span>
    </>
  ) : (
    sessionLabel
  );
  const canAdjustWorkspace =
    sessionState.status === "ready" &&
    (controllerState.status === "ready" ||
      controllerState.status === "draft" ||
      (controllerState.status === "error" && controllerState.dirty));
  const canSaveWorkspace =
    sessionState.status === "ready" &&
    (controllerState.status === "draft" ||
      (controllerState.status === "error" && controllerState.dirty));
  const canRecoverEvents =
    sessionState.status === "ready" &&
    data?.run !== null &&
    data?.run !== undefined &&
    !eventRecoveryPending;
  const navigation = {
    projectId: projectId ? String(projectId) : undefined,
    draftId: draftId ? String(draftId) : undefined,
    contractId: data?.contract
      ? String(data.contract.id)
      : contractId
        ? String(contractId)
        : undefined,
    runId: data?.run
      ? String(data.run.id)
      : routeRunId
        ? String(routeRunId)
        : undefined,
  };

  return (
    <ResearchShell
      status={railStatus}
      navigation={navigation}
      atlas={
        data ? (
          <>
            <p className="region-label">Project</p>
            <p className="region-placeholder">{data.project.name}</p>
            <p className="region-label">Run</p>
            <p className="region-placeholder">
              {data.run
                ? `${data.run.executionMode} / ${data.run.status}`
                : "未选择"}
            </p>
            {data.runs.length > 0 && (
              <label className="run-control">
                选择 Run
                <select
                  value={data.run?.id ?? ""}
                  onChange={(event) => {
                    const nextRun = data.runs.find(
                      (candidate) => candidate.id === event.target.value,
                    );
                    if (nextRun) void selectRun(nextRun);
                  }}
                  disabled={!canAdjustWorkspace}
                >
                  {data.runs.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.id} / {candidate.executionMode} /{" "}
                      {candidate.status}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <p className="region-label">Contract</p>
            <p className="region-placeholder">
              {data.contract
                ? `${data.contract.researchGoal} / v${data.contract.version}`
                : "未确认"}
            </p>
            <p className="region-label">Artifacts</p>
            {data.artifacts.map((artifact) => (
              <button
                key={artifact.id}
                type="button"
                className="atlas-item"
                onClick={() => void selectArtifact(artifact)}
                disabled={!canAdjustWorkspace}
              >
                {artifact.title}
              </button>
            ))}
          </>
        ) : (
          <p className="region-placeholder">等待 Project 上下文。</p>
        )
      }
      observatory={
        data?.selectedVersion ? (
          <>
            <p className="region-label">Artifact Version</p>
            <p className="region-placeholder">
              {data.selectedVersion.id} / v{data.selectedVersion.versionNumber}
            </p>
            <p className="region-placeholder">
              {data.selectedVersion.sourceMode} /{" "}
              {data.selectedVersion.contentHash}
            </p>
            {data.selectedEvidence && (
              <button
                type="button"
                className="atlas-item"
                onClick={() => void selectEvidence(data.selectedEvidence!)}
                disabled={!canAdjustWorkspace}
              >
                {data.selectedEvidence.id}
              </button>
            )}
            {data.selectedEvidence && (
              <p className="region-placeholder">
                {evidenceSummary(data.selectedEvidence)}
              </p>
            )}
          </>
        ) : (
          <p className="region-placeholder">
            选择 ArtifactVersion 后显示证据。
          </p>
        )
      }
      console={
        <div className="console-actions">
          <button
            type="button"
            onClick={() => {
              void runtime.workspaceController.save().catch(() => {});
            }}
            disabled={!canSaveWorkspace}
          >
            保存工作区
          </button>
          <button
            type="button"
            onClick={() => void recoverRunEvents()}
            disabled={!canRecoverEvents}
          >
            恢复运行事件
          </button>
          <button
            type="button"
            onClick={() => void createShare()}
            disabled={
              sessionState.status !== "ready" ||
              !data?.selectedVersion ||
              !data.selectedEvidence ||
              sharePending
            }
          >
            创建只读分享
          </button>
        </div>
      }
    >
      <section
        className="route-content workspace-page"
        aria-labelledby="route-title"
      >
        <h1 id="route-title">科研工作区</h1>
        <p className="status-line">{workspaceStatus(controllerState)}</p>
        {(sessionState.status === "error" ||
          sessionState.status === "expired") && (
          <section className="alert-panel" role="alert">
            <p>
              {sessionState.status === "expired"
                ? "会话已过期，请重新建立研究上下文。"
                : "无法建立研究会话。"}
            </p>
            <button type="button" onClick={sessionState.retry}>
              重新建立会话
            </button>
          </section>
        )}
        {loadState.status === "loading" && (
          <p aria-live="polite">正在读取研究产物。</p>
        )}
        {loadState.status === "empty" && <p>缺少 Project 或 Run 上下文。</p>}
        {loadState.status === "error" && (
          <section className="alert-panel" role="alert">
            <p>无法读取当前工作区，请重试。</p>
            <button type="button" onClick={() => void loadWorkspace()}>
              重新读取研究产物
            </button>
          </section>
        )}

        {controllerState.status === "conflict" && (
          <section className="alert-panel" role="alert">
            <h2>工作区版本冲突</h2>
            <p>本地更改尚未保存。</p>
            <p>
              服务器 revision{" "}
              {controllerState.latestSnapshot?.revision ?? "不可用"}
            </p>
            <button
              type="button"
              onClick={() => runtime.workspaceController.adoptLatest()}
              disabled={!controllerState.latestSnapshot}
            >
              采用服务器最新版本
            </button>
          </section>
        )}
        {controllerState.status === "error" && controllerState.dirty && (
          <section className="alert-panel" role="alert">
            <p>保存失败，本地更改仍保留。</p>
            <button
              type="button"
              onClick={() => {
                void runtime.workspaceController.save().catch(() => {});
              }}
              disabled={!canSaveWorkspace}
            >
              再次保存
            </button>
          </section>
        )}
        {controllerState.status === "error" && !controllerState.dirty && (
          <section className="alert-panel" role="alert">
            <p>无法恢复工作区，请重新读取。</p>
            <button type="button" onClick={() => void loadWorkspace()}>
              重新读取工作区
            </button>
          </section>
        )}
        {selectionError && (
          <p role="alert">无法选择当前 ArtifactVersion 或 Evidence。</p>
        )}
        {eventRecoveryError && <p role="alert">无法恢复运行事件，请重试。</p>}

        <label className="layout-control">
          布局
          <select
            value={
              controllerState.status === "ready" ||
              controllerState.status === "draft" ||
              controllerState.status === "saving" ||
              controllerState.status === "error"
                ? controllerState.draft.layoutPreset
                : "comparative"
            }
            onChange={(event) =>
              void runtime.workspaceController
                .setLayoutPreset(event.target.value)
                .catch(() => {})
            }
            disabled={!canAdjustWorkspace}
          >
            <option value="comparative">对照</option>
            <option value="focus">聚焦</option>
            <option value="grid">网格</option>
          </select>
        </label>

        {data && (
          <>
            <section className="work-panel" aria-labelledby="contract-title">
              <h2 id="contract-title">Research Contract</h2>
              <p>{data.contract?.researchGoal ?? "尚无已确认 Contract。"}</p>
              {data.contract && (
                <p>字段：{data.contract.requestedFields.join("、")}</p>
              )}
            </section>
            <section className="work-panel" aria-labelledby="run-title">
              <h2 id="run-title">Research Run</h2>
              <p>
                {data.run
                  ? `${data.run.status} / ${data.run.progress}% / ${data.run.executionMode}`
                  : "未选择 Run"}
              </p>
              <ol className="event-list">
                {data.events.map((event) => (
                  <li key={`${event.runId}-${event.sequence}`}>
                    {event.sequence}. {event.publicMessage}
                  </li>
                ))}
              </ol>
            </section>

            {data.selectedArtifact && data.selectedVersion && (
              <section className="work-panel" aria-labelledby="artifact-title">
                <h2 id="artifact-title">{data.selectedArtifact.title}</h2>
                <p>
                  {data.selectedArtifact.kind} / v
                  {data.selectedVersion.versionNumber} /{" "}
                  {data.selectedVersion.sourceMode}
                </p>
                <p>{data.selectedVersion.contentHash}</p>
              </section>
            )}

            {data.selectedEvidence && (
              <section className="work-panel" aria-labelledby="evidence-title">
                <h2 id="evidence-title">Evidence</h2>
                <p>{data.selectedEvidence.id}</p>
                <p>{evidenceSummary(data.selectedEvidence)}</p>
                <p>{data.selectedEvidence.quoteOrValue ?? "无公开值"}</p>
              </section>
            )}

            <section className="work-panel" aria-labelledby="share-title">
              <h2 id="share-title">Share</h2>
              {shareUrl && (
                <Link className="text-link" to={shareUrl}>
                  打开只读分享
                </Link>
              )}
              {shareFeedback === "unavailable" && (
                <p role="alert">共享资源不可用，可能已撤销或过期。</p>
              )}
              {shareFeedback === "network" && (
                <p role="alert">无法完成分享操作，请检查网络后重试。</p>
              )}
              <ul className="share-list">
                {data.shares.map((share) => (
                  <li key={share.id}>
                    <span>{share.title}</span>
                    <span>{share.status}</span>
                    {share.status === "active" && (
                      <button
                        type="button"
                        onClick={() => void revokeShare(share)}
                        aria-label={`撤销 ${share.title}`}
                      >
                        撤销
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          </>
        )}
      </section>
    </ResearchShell>
  );
}
