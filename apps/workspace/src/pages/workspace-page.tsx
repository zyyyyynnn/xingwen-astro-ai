import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useRouteContext } from "@tanstack/react-router";
import type { RepositorySet } from "@xingwen/data-access";
import type { PaperCandidateReview, RunStatus } from "@xingwen/domain";
import { BrandMark } from "@xingwen/ui";
import {
  getContextRailMode,
  getMainStageView,
  type WorkspaceState,
} from "@xingwen/workspace-core";

import { ArtifactCanvas } from "../components/artifact-canvas";
import { MissionHeader } from "../components/mission-header";
import { MissionSpine, phaseFromRunStatus } from "../components/mission-spine";
import {
  evidenceSummary,
  ProvenanceObservatory,
} from "../components/provenance-observatory";
import { ResearchCommandMenu } from "../components/research-command-menu";
import type { CommandGroup } from "../components/research-command-menu";
import {
  ResearchComposer,
  type AttachedObject,
} from "../components/research-composer";
import {
  ResearchContextRail,
  type ContextHistoryEntry,
  type ContextRailScene,
} from "../components/research-context-rail";
import type {
  NavigatorProject,
  ProjectUserStatus,
} from "../components/research-navigator";
import { ResearchNavigator } from "../components/research-navigator";
import { WorkspaceShell } from "../components/workspace-shell";
import { useControllerState } from "../hooks/use-controller-state";
import { usePrivateSession } from "../hooks/use-private-session";
import { useWorkspaceSessionState } from "../hooks/use-workspace-session-state";
import { useProjectsQuery } from "../queries/workspace-queries";

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

function belongsToProject(state: WorkspaceState, projectId: EntityId): boolean {
  return state.status !== "idle" && state.projectId === projectId;
}

function deriveUserStatus(
  project: Project,
  runStatus: RunStatus | null,
): ProjectUserStatus {
  if (!project.latestRunId) return "draft";
  if (!runStatus) return "draft";
  switch (runStatus) {
    case "completed":
      return "completed";
    case "failed":
    case "cancelled":
      return "failed";
    case "waiting_for_input":
      return "needs_review";
    default:
      return "running";
  }
}

function mapProjectToNavigator(
  project: Project,
  activeRunStatus: RunStatus | null,
): NavigatorProject {
  return {
    id: String(project.id),
    name: project.name,
    userStatus: deriveUserStatus(project, activeRunStatus),
    updatedAt: project.updatedAt,
    latestRunId: project.latestRunId ? String(project.latestRunId) : null,
  };
}

const PHASE_TO_VIEW: readonly ContextRailScene[] = [
  "brief",
  "brief",
  "active",
  "active",
  "source_review",
  "completion",
];

export function WorkspacePage({
  projectId: projectIdProp,
  draftId: draftIdProp,
  contractId: contractIdProp,
  runId: runIdProp,
}: WorkspacePageProps) {
  const runtime = useRouteContext({ from: "/workspace" });
  const navigate = useNavigate();
  const sessionState = usePrivateSession(runtime);
  const controllerState = useControllerState(runtime.workspaceController);
  const sessionControllerState = useWorkspaceSessionState(
    runtime.workspaceController,
  );
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
  const [selectedRun, setSelectedRun] = useState<{
    readonly projectId: EntityId;
    readonly runId: EntityId;
  } | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [shareFeedback, setShareFeedback] = useState<ShareFeedback>(null);
  const [sharePending, setSharePending] = useState(false);
  const [selectionError, setSelectionError] = useState(false);
  const [eventRecoveryError, setEventRecoveryError] = useState(false);
  const [eventRecoveryPending, setEventRecoveryPending] = useState(false);
  const [selectedCandidate, setSelectedCandidate] =
    useState<PaperCandidateReview | null>(null);
  const [composerMode, setComposerMode] = useState<"docked" | "focus">(
    "docked",
  );
  const [attachedObjects, setAttachedObjects] = useState<AttachedObject[]>([]);
  const [commandMenuOpen, setCommandMenuOpen] = useState(false);
  const [pinnedProjectIds, setPinnedProjectIds] = useState<readonly string[]>(
    [],
  );
  const [recentProjectIds, setRecentProjectIds] = useState<readonly string[]>(
    [],
  );
  const [lastTrackedProjectId, setLastTrackedProjectId] =
    useState<EntityId | null>(null);
  const loadSequence = useRef(0);
  const selectionSequence = useRef(0);
  const recoverySequence = useRef(0);
  const shareRequestPending = useRef(false);
  const selectedRunId =
    selectedRun?.projectId === projectId ? selectedRun.runId : null;

  const projectsQuery = useProjectsQuery(runtime.repositories);
  const projects = useMemo(
    () => projectsQuery.data ?? [],
    [projectsQuery.data],
  );

  const loadWorkspace = useCallback(async () => {
    const request = ++loadSequence.current;
    const isCurrent = () => request === loadSequence.current;
    if (sessionState.status !== "ready") return;
    if (!projectId) {
      if (isCurrent()) setLoadState({ status: "empty" });
      return;
    }

    setLoadState({ status: "loading" });
    setSelectedCandidate(null);
    try {
      const workspaceState = runtime.workspaceController.getState();
      if (
        !belongsToProject(workspaceState, projectId) ||
        !preservesLocalWorkspaceState(workspaceState)
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

  if (
    projectId &&
    sessionState.status === "ready" &&
    lastTrackedProjectId !== projectId
  ) {
    setLastTrackedProjectId(projectId);
    setRecentProjectIds((prev) => {
      const id = String(projectId);
      const filtered = prev.filter((p) => p !== id);
      return [id, ...filtered].slice(0, 8);
    });
  }

  const data = loadState.status === "ready" ? loadState.data : null;

  const navigatorProjects = useMemo<readonly NavigatorProject[]>(() => {
    return projects.map((project) =>
      mapProjectToNavigator(
        project,
        project.id === data?.project.id ? (data.run?.status ?? null) : null,
      ),
    );
  }, [projects, data]);

  const selectRun = useCallback(
    async (run: ResearchRun) => {
      const selection = ++selectionSequence.current;
      try {
        await runtime.workspaceController.setActiveRun(run.id);
        if (selection !== selectionSequence.current) return;
        if (!data) return;
        setSelectedCandidate(null);
        setSelectedRun({ projectId: data.project.id, runId: run.id });
        setSelectionError(false);
      } catch {
        if (selection === selectionSequence.current) setSelectionError(true);
      }
    },
    [data, runtime.workspaceController],
  );

  const selectArtifact = useCallback(
    async (artifact: Artifact) => {
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
        setSelectedCandidate(null);
        setSelectionError(false);
      } catch {
        if (selection === selectionSequence.current) setSelectionError(true);
      }
    },
    [runtime.repositories.artifacts, runtime.workspaceController],
  );

  const selectCandidate = (candidate: PaperCandidateReview) => {
    setSelectedCandidate(candidate);
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

  const handleSelectProject = (project: NavigatorProject) => {
    void navigate({
      to: "/workspace",
      search: { projectId: project.id },
    });
  };

  const handleCreateProject = () => {
    void navigate({ to: "/", search: {} });
  };

  const handleTogglePin = (projectId: string) => {
    setPinnedProjectIds((prev) =>
      prev.includes(projectId)
        ? prev.filter((id) => id !== projectId)
        : [...prev, projectId],
    );
  };

  const handleContextRailModeChange = (
    mode: "hidden" | "summary" | "detail",
  ) => {
    void runtime.workspaceController.setContextRailMode(mode).catch(() => {});
  };

  const handleContextCardClick = (cardType: string) => {
    void runtime.workspaceController
      .setActiveContextPanel(cardType)
      .catch(() => {});
  };

  const handleComposerSubmit = (
    input: string,
    objects?: readonly AttachedObject[],
  ) => {
    if (!data?.run) return;
    const runId = data.run.id;
    const runRef = {
      artifactVersionId: null,
      objectType: "run",
      objectId: runId,
    };
    runtime.workspaceController.pushContextHistory(runRef);
    for (const object of objects ?? []) {
      runtime.workspaceController.pushContextHistory({
        artifactVersionId:
          object.kind === "artifact" ? (object.id as EntityId) : null,
        objectType: object.kind,
        objectId: object.id as EntityId,
      });
    }
    setLoadState((current) =>
      current.status === "ready" && current.data.run?.id === runId
        ? {
            status: "ready",
            data: {
              ...current.data,
              events: [
                ...current.data.events,
                {
                  runId,
                  sequence: current.data.events.length + 1,
                  eventType: "user_input" as EntityId,
                  stepKey: null,
                  progress: null,
                  publicMessage: objects?.length
                    ? `${input}（附加 ${objects.length} 个对象）`
                    : input,
                  artifactVersionIds:
                    objects
                      ?.filter((object) => object.kind === "artifact")
                      .map((object) => object.id as EntityId) ?? [],
                  occurredAt: new Date().toISOString(),
                },
              ],
            },
          }
        : current,
    );
    setAttachedObjects([]);
  };

  const handleAttachObject = (object: AttachedObject) => {
    setAttachedObjects((prev) =>
      prev.some((item) => item.id === object.id) ? prev : [...prev, object],
    );
  };

  const handleDetachObject = (id: string) => {
    setAttachedObjects((prev) => prev.filter((item) => item.id !== id));
  };

  const handlePhaseClick = (phase: number) => {
    const view = PHASE_TO_VIEW[phase] ?? "active";
    void runtime.workspaceController.setMainStageView(view).catch(() => {});
  };

  const handleMissionAction = () => {
    if (!data?.run) {
      void navigate({
        to: "/tour",
        search: projectId ? { projectId: String(projectId) } : {},
      });
      return;
    }
    const status = data.run.status;
    if (status === "completed") {
      void runtime.workspaceController
        .setMainStageView("completion")
        .catch(() => {});
    } else if (status === "waiting_for_input") {
      void runtime.workspaceController
        .setMainStageView("source_review")
        .catch(() => {});
    } else if (status === "failed" || status === "cancelled") {
      void navigate({
        to: "/tour",
        search: { projectId: String(data.project.id) },
      });
    } else {
      void runtime.workspaceController
        .setMainStageView("active")
        .catch(() => {});
    }
  };

  const handleRailWidthChange = (width: number) => {
    runtime.workspaceController.setRailWidth(width);
  };

  const handleClearHistory = () => {
    runtime.workspaceController.clearContextHistory();
  };

  const commandGroups = useMemo<readonly CommandGroup[]>(() => {
    const groups: CommandGroup[] = [];
    groups.push({
      label: "导航",
      items: [
        {
          id: "nav-home",
          label: "返回入口",
          onSelect: () => void navigate({ to: "/", search: {} }),
        },
        {
          id: "nav-tour",
          label: "进入引导",
          onSelect: () =>
            void navigate({
              to: "/tour",
              search: projectId ? { projectId: String(projectId) } : {},
            }),
        },
        {
          id: "nav-workspace",
          label: "进入工作区",
          onSelect: () =>
            void navigate({
              to: "/workspace",
              search: projectId ? { projectId: String(projectId) } : {},
            }),
        },
      ],
    });
    if (data?.runs.length) {
      groups.push({
        label: "切换 Run",
        items: data.runs.map((run) => ({
          id: `run-${run.id}`,
          label: `${run.id} / ${run.executionMode} / ${run.status}`,
          onSelect: () => void selectRun(run),
        })),
      });
    }
    if (data?.artifacts.length) {
      groups.push({
        label: "选择产物",
        items: data.artifacts.map((artifact) => ({
          id: `artifact-${artifact.id}`,
          label: artifact.title,
          onSelect: () => void selectArtifact(artifact),
        })),
      });
    }
    groups.push({
      label: "视图",
      items: [
        {
          id: "view-brief",
          label: "概览",
          onSelect: () =>
            void runtime.workspaceController
              .setMainStageView("brief")
              .catch(() => {}),
        },
        {
          id: "view-active",
          label: "活动研究",
          onSelect: () =>
            void runtime.workspaceController
              .setMainStageView("active")
              .catch(() => {}),
        },
        {
          id: "view-artifact-review",
          label: "产物复核",
          onSelect: () =>
            void runtime.workspaceController
              .setMainStageView("artifact_review")
              .catch(() => {}),
        },
        {
          id: "view-source-review",
          label: "来源复核",
          onSelect: () =>
            void runtime.workspaceController
              .setMainStageView("source_review")
              .catch(() => {}),
        },
        {
          id: "view-completion",
          label: "完成总结",
          onSelect: () =>
            void runtime.workspaceController
              .setMainStageView("completion")
              .catch(() => {}),
        },
      ],
    });
    return groups;
  }, [
    data,
    navigate,
    projectId,
    runtime.workspaceController,
    selectArtifact,
    selectRun,
  ]);

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
  const contextualSearch = {
    ...(navigation.projectId ? { projectId: navigation.projectId } : {}),
    ...(navigation.draftId ? { draftId: navigation.draftId } : {}),
    ...(navigation.contractId ? { contractId: navigation.contractId } : {}),
    ...(navigation.runId ? { runId: navigation.runId } : {}),
  };
  const currentArtifactForRail =
    data?.selectedArtifact && data?.selectedVersion
      ? {
          title: data.selectedArtifact.title,
          kind: data.selectedArtifact.kind,
          version: data.selectedVersion.versionNumber,
          status: data.run?.status ?? "未选择",
        }
      : null;
  const attachableCandidates = useMemo<readonly AttachedObject[]>(() => {
    const candidates: AttachedObject[] = [];
    if (data?.selectedArtifact && data?.selectedVersion) {
      candidates.push({
        id: String(data.selectedVersion.id),
        label: `${data.selectedArtifact.title} v${data.selectedVersion.versionNumber}`,
        kind: "artifact",
      });
    }
    if (data?.selectedEvidence) {
      candidates.push({
        id: String(data.selectedEvidence.id),
        label: `Evidence ${data.selectedEvidence.id}`,
        kind: "evidence",
      });
    }
    return candidates;
  }, [data]);
  const mainStageView = getMainStageView(controllerState);
  const railScene = mainStageView as ContextRailScene;
  const missionContext = data?.contract
    ? {
        researchGoal: data.contract.researchGoal,
        requestedFields: data.contract.requestedFields,
      }
    : null;
  const contextHistoryEntries: readonly ContextHistoryEntry[] =
    sessionControllerState.contextHistory.map((ref, index) => ({
      id: `${ref.objectType}-${ref.objectId}-${index}`,
      label: String(ref.objectId),
      kind: ref.objectType,
    }));
  const railWidth = sessionControllerState.railWidth ?? undefined;

  return (
    <WorkspaceShell
      navigator={
        <ResearchNavigator
          projects={navigatorProjects}
          activeProjectId={projectId ? String(projectId) : null}
          pinnedProjectIds={pinnedProjectIds}
          recentProjectIds={recentProjectIds}
          onSelectProject={handleSelectProject}
          onCreateProject={handleCreateProject}
          onTogglePin={handleTogglePin}
          disabled={sessionState.status !== "ready"}
        />
      }
      missionHeader={
        <MissionHeader
          project={data?.project ?? null}
          contract={data?.contract ?? null}
          run={data?.run ?? null}
          onPrimaryAction={handleMissionAction}
          primaryActionDisabled={!canAdjustWorkspace}
        />
      }
      missionSpine={
        <MissionSpine
          currentPhase={phaseFromRunStatus(data?.run?.status ?? null)}
          onPhaseClick={handlePhaseClick}
        />
      }
      contextRail={
        <ResearchContextRail
          mode={getContextRailMode(controllerState)}
          scene={railScene}
          pendingReviewCount={
            data?.events.filter((e) => e.publicMessage.includes("review"))
              .length
          }
          currentArtifact={currentArtifactForRail}
          missionContext={missionContext}
          contextHistory={contextHistoryEntries}
          railWidth={railWidth}
          onModeChange={handleContextRailModeChange}
          onCardClick={handleContextCardClick}
          onClearHistory={handleClearHistory}
          onRailWidthChange={handleRailWidthChange}
        />
      }
      composer={
        <ResearchComposer
          mode={composerMode}
          onSubmit={handleComposerSubmit}
          onModeChange={setComposerMode}
          disabled={!data?.run || sessionState.status !== "ready"}
          attachedObjects={attachedObjects}
          attachableCandidates={attachableCandidates}
          onAttachObject={handleAttachObject}
          onDetachObject={handleDetachObject}
        />
      }
      headerBrand={
        <>
          <BrandMark />
          <nav aria-label="主要导航">
            <Link to="/" activeOptions={{ exact: true }}>
              入口
            </Link>
            <Link to="/tour" search={contextualSearch}>
              引导
            </Link>
            <Link to="/workspace" search={contextualSearch}>
              工作区
            </Link>
          </nav>
        </>
      }
      headerBreadcrumb={
        <span className="rail-status" aria-label="当前状态">
          {railStatus}
        </span>
      }
      headerActions={
        <div className="console-actions">
          <button
            type="button"
            onClick={() => setCommandMenuOpen(true)}
            aria-label="打开命令面板"
          >
            命令面板 (Ctrl+K)
          </button>
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
      <ResearchCommandMenu
        open={commandMenuOpen}
        onOpenChange={setCommandMenuOpen}
        groups={commandGroups}
      />
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
          主舞台视图
          <select
            value={mainStageView}
            onChange={(event) =>
              void runtime.workspaceController
                .setMainStageView(event.target.value)
                .catch(() => {})
            }
            disabled={!canAdjustWorkspace}
          >
            <option value="brief">概览</option>
            <option value="active">活动</option>
            <option value="artifact_review">产物复核</option>
            <option value="source_review">来源复核</option>
            <option value="completion">完成</option>
          </select>
        </label>

        {data && (
          <>
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

            {data.artifacts.length > 0 && (
              <details className="region-details" open>
                <summary>Artifacts</summary>
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
              </details>
            )}

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
              <ArtifactCanvas
                artifact={data.selectedArtifact}
                version={data.selectedVersion}
                paperAcquisition={runtime.repositories.paperAcquisition}
                paperSummary={runtime.repositories.paperSummary}
                comparisonArtifactVersionIds={data.artifacts
                  .filter((artifact) => artifact.kind === "paper_summary")
                  .flatMap((artifact) =>
                    artifact.latestVersionId === null
                      ? []
                      : [artifact.latestVersionId],
                  )
                  .slice(0, 3)}
                executionMode={data.run?.executionMode ?? null}
                ready={sessionState.status === "ready"}
                disabled={!canAdjustWorkspace}
                selectedCandidateId={
                  selectedCandidate
                    ? String(selectedCandidate.candidateId)
                    : null
                }
                selectedEvidenceId={
                  data.selectedEvidence
                    ? String(data.selectedEvidence.id)
                    : null
                }
                onSelectCandidate={selectCandidate}
                onSelectEvidence={(evidence) => void selectEvidence(evidence)}
              />
            )}

            {data.selectedEvidence && (
              <section className="work-panel" aria-labelledby="evidence-title">
                <h2 id="evidence-title">Evidence</h2>
                <p>{data.selectedEvidence.id}</p>
                <p>{evidenceSummary(data.selectedEvidence)}</p>
                <p>{data.selectedEvidence.quoteOrValue ?? "无公开值"}</p>
              </section>
            )}

            <section className="work-panel" aria-labelledby="provenance-title">
              <h2 id="provenance-title">Provenance Observatory</h2>
              <ProvenanceObservatory
                version={data?.selectedVersion ?? null}
                evidence={data?.selectedEvidence ?? null}
                candidate={selectedCandidate}
                canAdjust={canAdjustWorkspace}
                onSelectEvidence={(evidence) => void selectEvidence(evidence)}
              />
            </section>

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
    </WorkspaceShell>
  );
}
