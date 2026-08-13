import { useMutation, useQuery } from "@tanstack/react-query";
import {
  CASE_KEY,
  parseEntityId,
  type ContentHash,
  type DomainEntityId,
} from "@xingwen/domain";
import type { ProjectViewModel } from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  Button,
  Skeleton,
  Toaster,
  toast,
} from "@xingwen/ui";
import { useCallback, useEffect, useState } from "react";

import {
  OpenHandsWorkspaceRoot,
  type ResearchWorkspaceRuntime,
} from "../upstream/openhands/src/root";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { ProjectCreateDialog } from "./components/project-create-dialog";
import { ProjectActionDialogs } from "./components/project-action-dialogs";
import { ScientificArtifactPanel } from "./components/scientific-artifact-panel";
import { ResearchContractReviewDialog } from "./components/research-contract-review-dialog";
import { ResearchInspector } from "./components/research-inspector";
import { ResearchThread } from "./components/research-thread";
import { ResearchProcessProjection } from "./components/research-process-projection";
import {
  deriveResearchPresentation,
  type ResearchPresentation,
} from "./presentation/research-presentation";

interface WorkspaceEntryProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly onOpenProject: (projectId: string) => void;
}

function safeError(
  runtime: WorkspaceRuntimeBoundaries,
  error: unknown,
): string {
  return runtime.researchAdapter.toPublicApplicationError(error).safeMessage;
}

function returnHome(runtime: WorkspaceRuntimeBoundaries): void {
  globalThis.location.assign(runtime.siteUrl);
}

const PINNED_PROJECTS_KEY = "xingwen.pinned-projects";
const EMPTY_PROJECTS: readonly ProjectViewModel[] = Object.freeze([]);

function readPinnedProjects(): readonly string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(
      window.localStorage.getItem(PINNED_PROJECTS_KEY) ?? "[]",
    );
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

function writePinnedProjects(projectIds: readonly string[]): void {
  window.localStorage.setItem(PINNED_PROJECTS_KEY, JSON.stringify(projectIds));
}

function usePinnedProjects(projects: readonly ProjectViewModel[]) {
  const [pinnedProjects, setPinnedProjects] =
    useState<readonly string[]>(readPinnedProjects);
  const validProjectIds = new Set<string>(
    projects.map((project) => project.id),
  );
  const visiblePinnedProjects = pinnedProjects.filter((projectId) =>
    validProjectIds.has(projectId),
  );
  return {
    pinnedProjects: visiblePinnedProjects,
    togglePinned(projectId: string) {
      setPinnedProjects((current) => {
        const validCurrent = current.filter((item) =>
          validProjectIds.has(item),
        );
        const next = validCurrent.includes(projectId)
          ? validCurrent.filter((item) => item !== projectId)
          : [...validCurrent, projectId];
        writePinnedProjects(next);
        return next;
      });
    },
  };
}

function useProjectCreation({ runtime, onOpenProject }: WorkspaceEntryProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const createProject = useMutation(
    runtime.application.mutations.projectCreate(),
  );
  const errorMessage = createProject.error
    ? safeError(runtime, createProject.error)
    : null;
  return {
    setDialogOpen,
    dialog: (
      <ProjectCreateDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        pending={createProject.isPending}
        errorMessage={errorMessage}
        onCreate={async (input) => {
          const project = await createProject.mutateAsync({
            ...input,
            caseKey: CASE_KEY,
          });
          setDialogOpen(false);
          onOpenProject(project.id);
        }}
      />
    ),
  };
}

function useProjectActions({
  runtime,
  projects,
  onDeleted,
}: {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projects: readonly ProjectViewModel[];
  readonly onDeleted: (projectId: string) => void;
}) {
  const [renameProjectId, setRenameProjectId] = useState<string | null>(null);
  const [deleteProjectId, setDeleteProjectId] = useState<string | null>(null);
  const updateProject = useMutation(
    runtime.application.mutations.projectUpdate(),
  );
  const deleteProject = useMutation(
    runtime.application.mutations.projectDelete(),
  );
  const renameProject =
    projects.find((project) => project.id === renameProjectId) ?? null;
  const projectToDelete =
    projects.find((project) => project.id === deleteProjectId) ?? null;
  const error = updateProject.error ?? deleteProject.error;
  return {
    requestRename: setRenameProjectId,
    requestDelete: setDeleteProjectId,
    dialog: (
      <ProjectActionDialogs
        renameProject={renameProject}
        deleteProject={projectToDelete}
        pending={updateProject.isPending || deleteProject.isPending}
        errorMessage={error ? safeError(runtime, error) : null}
        onCloseRename={() => setRenameProjectId(null)}
        onCloseDelete={() => setDeleteProjectId(null)}
        onRename={async (name) => {
          if (!renameProject) return;
          await updateProject.mutateAsync({
            projectId: renameProject.id,
            expectedRevision: renameProject.revision,
            input: { name },
          });
          setRenameProjectId(null);
        }}
        onDelete={async () => {
          if (!projectToDelete) return;
          await deleteProject.mutateAsync({
            projectId: projectToDelete.id,
            expectedRevision: projectToDelete.revision,
          });
          setDeleteProjectId(null);
          onDeleted(projectToDelete.id);
        }}
      />
    ),
  };
}

function projectNavigation(
  projects: readonly ProjectViewModel[],
  projectId: DomainEntityId | null,
  pinnedProjects: readonly string[],
  currentPresentation?: ResearchPresentation,
) {
  const pinned = new Set(pinnedProjects);
  return [...projects]
    .sort((left, right) => {
      const pinnedOrder =
        Number(pinned.has(right.id)) - Number(pinned.has(left.id));
      return pinnedOrder || right.updatedAt.localeCompare(left.updatedAt);
    })
    .map((project) => {
      const presentation =
        project.id === projectId && currentPresentation
          ? currentPresentation
          : deriveResearchPresentation({ project });
      return {
        id: project.id,
        title: project.name,
        status: presentation.statusLabel,
        updatedAt: project.updatedAt,
        current: project.id === projectId,
        pinned: pinned.has(project.id),
      };
    });
}

function runtimeForEntry(
  runtime: WorkspaceRuntimeBoundaries,
  projects: readonly ProjectViewModel[],
  pinnedProjects: readonly string[],
  onOpenProject: (projectId: string) => void,
  onNewResearch: () => void,
  onToggleProjectPinned: (projectId: string) => void,
  onRequestProjectRename: (projectId: string) => void,
  onRequestProjectDelete: (projectId: string) => void,
): ResearchWorkspaceRuntime {
  return {
    project: null,
    navigation: {
      projects: projectNavigation(projects, null, pinnedProjects),
      onOpenProject,
      onNewResearch,
      onReturnHome: () => returnHome(runtime),
      onToggleProjectPinned,
      onRequestProjectRename,
      onRequestProjectDelete,
    },
    composer: null,
    activation: {
      title: projects.length === 0 ? "建立第一个研究项目" : "选择一个研究项目",
      description:
        projects.length === 0
          ? "研究项目会保存对话、协议和真实运行引用。"
          : "从左侧导航选择研究项目，继续同一段研究对话。",
      actionLabel: projects.length === 0 ? "新建研究项目" : "新建研究项目",
      onAction: onNewResearch,
    },
    threadPanel: <div className="research-thread-entry-placeholder" />,
    inspectorPanel: null,
  };
}

export function WorkspaceEntry({
  runtime,
  onOpenProject,
}: WorkspaceEntryProps) {
  const projects = useQuery(runtime.application.queries.projects());
  const creation = useProjectCreation({ runtime, onOpenProject });
  const projectList = projects.data ?? EMPTY_PROJECTS;
  const pinned = usePinnedProjects(projectList);
  const actions = useProjectActions({
    runtime,
    projects: projectList,
    onDeleted: () => undefined,
  });
  const content = projects.isError ? (
    <section className="route-content">
      <h1>研究项目载入失败</h1>
      <Alert variant="destructive">
        <AlertDescription>
          {safeError(runtime, projects.error)}
        </AlertDescription>
      </Alert>
    </section>
  ) : projects.isPending ? (
    <section className="route-content" aria-busy="true">
      <h1>正在载入研究项目</h1>
      <Skeleton className="workspace-loading-skeleton" />
    </section>
  ) : (
    <WorkspaceShell
      runtime={runtimeForEntry(
        runtime,
        projectList,
        pinned.pinnedProjects,
        onOpenProject,
        () => creation.setDialogOpen(true),
        pinned.togglePinned,
        actions.requestRename,
        actions.requestDelete,
      )}
    />
  );
  return (
    <>
      {content}
      {creation.dialog}
      {actions.dialog}
    </>
  );
}

interface WorkspaceHostProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly onOpenProject: (projectId: string) => void;
  readonly onProjectDeleted: () => void;
}

export function WorkspaceHost({
  runtime,
  projectId,
  onOpenProject,
  onProjectDeleted,
}: WorkspaceHostProps) {
  const [reviewOpen, setReviewOpen] = useState(false);
  const [explicitArtifactVersionId, setExplicitArtifactVersionId] =
    useState<DomainEntityId | null>(null);
  const [planFocusRequest, setPlanFocusRequest] = useState(0);
  const [message, setMessage] = useState("");
  const [answerToQuestionId, setAnswerToQuestionId] = useState<string | null>(
    null,
  );
  const [pendingTurn, setPendingTurn] = useState<{
    readonly actionId: string;
    readonly message: string;
  } | null>(null);
  const project = useQuery(runtime.application.queries.project(projectId));
  const researchCatalog = useQuery(
    runtime.application.queries.researchCatalog(projectId),
  );
  const projects = useQuery(runtime.application.queries.projects());
  const creation = useProjectCreation({ runtime, onOpenProject });
  const projectList = projects.data ?? EMPTY_PROJECTS;
  const pinned = usePinnedProjects(projectList);
  const actions = useProjectActions({
    runtime,
    projects: projectList,
    onDeleted: (deletedProjectId) => {
      if (deletedProjectId === projectId) onProjectDeleted();
    },
  });
  const activeDraftId = project.data?.activeDraftId ?? null;
  const draft = useQuery({
    ...runtime.application.queries.draft(
      projectId,
      activeDraftId as DomainEntityId,
    ),
    enabled: activeDraftId !== null,
  });
  const activeContractId = project.data?.activeContractId ?? null;
  const contract = useQuery({
    ...runtime.application.queries.contract(
      projectId,
      activeContractId as DomainEntityId,
    ),
    enabled: activeContractId !== null,
  });
  const runId = project.data?.latestRunId ?? null;
  const run = useQuery({
    ...runtime.application.queries.run(projectId, runId as DomainEntityId),
    enabled: runId !== null,
  });
  const steps = useQuery({
    ...runtime.application.queries.runSteps(projectId, runId as DomainEntityId),
    enabled: runId !== null,
  });
  const artifacts = useQuery({
    ...runtime.application.queries.runArtifacts(
      projectId,
      runId as DomainEntityId,
    ),
    enabled: runId !== null,
  });
  const availableArtifactVersionIds = [...(artifacts.data ?? [])]
    .filter((artifact) =>
      ["analysis_report", "visualization", "model_evaluation"].includes(
        artifact.kind,
      ),
    )
    .filter(
      (
        artifact,
      ): artifact is typeof artifact & {
        readonly latestVersionId: DomainEntityId;
      } => artifact.latestVersionId !== null,
    )
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .map((artifact) => artifact.latestVersionId);
  const selectedArtifactVersionId =
    explicitArtifactVersionId !== null &&
    availableArtifactVersionIds.includes(explicitArtifactVersionId)
      ? explicitArtifactVersionId
      : (availableArtifactVersionIds[0] ?? null);
  const selectedArtifact = artifacts.data?.find(
    (artifact) => artifact.latestVersionId === selectedArtifactVersionId,
  );
  const scientificArtifact = useQuery({
    ...runtime.application.queries.scientificArtifact(
      projectId,
      selectedArtifactVersionId as DomainEntityId,
    ),
    enabled:
      selectedArtifactVersionId !== null &&
      selectedArtifact !== undefined &&
      ["analysis_report", "visualization", "model_evaluation"].includes(
        selectedArtifact.kind,
      ),
  });
  const loadScientificContent = useCallback(
    (contentHash: ContentHash) => {
      if (selectedArtifactVersionId === null) {
        return Promise.reject(new Error("尚未选择科学制品版本。"));
      }
      return runtime.repositories.scientificArtifacts.getContent(
        selectedArtifactVersionId,
        contentHash,
      );
    },
    [runtime.repositories.scientificArtifacts, selectedArtifactVersionId],
  );
  const events = useQuery({
    ...runtime.application.queries.runEvents(
      projectId,
      runId as DomainEntityId,
    ),
    enabled: false,
  });
  useEffect(() => {
    if (runId === null) return undefined;
    const feed = runtime.application.createRunEventFeed(projectId, runId);
    feed.start();
    return () => feed.stop();
  }, [projectId, runId, runtime.application]);
  const thread = useQuery(runtime.application.queries.thread(projectId));
  const submitTurn = useMutation(
    runtime.application.mutations.researchTurnSubmit(),
  );
  const confirmContract = useMutation(
    runtime.application.mutations.contractConfirm(),
  );
  const updateDraft = useMutation(runtime.application.mutations.draftUpdate());
  const createRun = useMutation(runtime.application.mutations.runCreate());

  if (project.isError) {
    return (
      <section className="route-content">
        <h1>研究项目载入失败</h1>
        <Alert variant="destructive">
          <AlertDescription>
            {safeError(runtime, project.error)}
          </AlertDescription>
        </Alert>
      </section>
    );
  }
  if (project.isPending || !project.data) {
    return (
      <section className="route-content" aria-busy="true">
        <h1>正在载入研究项目</h1>
        <Skeleton className="workspace-loading-skeleton" />
      </section>
    );
  }

  const error =
    submitTurn.error ??
    updateDraft.error ??
    confirmContract.error ??
    createRun.error ??
    thread.error;
  const errorMessage = error ? safeError(runtime, error) : null;
  const pendingAction = updateDraft.isPending
    ? "save-draft"
    : confirmContract.isPending
      ? "confirm-contract"
      : createRun.isPending
        ? "create-run"
        : null;
  const currentDraft = draft.data ?? null;
  const currentContract = contract.data ?? null;
  const currentRun = run.data ?? null;
  const stepsData = steps.data ?? [];
  const threadEntries = thread.data ?? [];
  const threadUnavailable = thread.isError && thread.data === undefined;
  const threadReady = thread.data !== undefined;
  const hasPersistedConversation = threadEntries.length > 0;
  const hasStartedConversation =
    hasPersistedConversation || pendingTurn !== null;
  const researchPresentation = deriveResearchPresentation({
    project: project.data,
    entries: threadEntries,
    draft: currentDraft,
    contract: currentContract,
    run: currentRun,
    steps: stepsData,
    pendingActionId: pendingTurn?.actionId ?? null,
  });
  const submitMessage = async (nextMessage: string) => {
    const outgoingMessage = nextMessage.trim();
    if (!outgoingMessage || submitTurn.isPending) return;
    const parsedAnswerId =
      answerToQuestionId === null ? null : parseEntityId(answerToQuestionId);
    if (answerToQuestionId !== null && parsedAnswerId === null) {
      throw new Error("澄清问题标识无效。");
    }
    const actionId = runtime.application.createResearchTurnActionId();
    setPendingTurn({ actionId, message: outgoingMessage });
    setMessage("");
    try {
      await submitTurn.mutateAsync({
        projectId,
        message: outgoingMessage,
        answerToQuestionId: parsedAnswerId,
        actionId,
      });
      setAnswerToQuestionId(null);
    } catch (error) {
      setMessage(outgoingMessage);
      toast.error("消息发送失败", {
        description: safeError(runtime, error),
      });
      throw error;
    } finally {
      setPendingTurn(null);
    }
  };
  const threadPanel = (
    <ResearchThread
      entries={threadEntries}
      loading={thread.isPending}
      loadError={threadUnavailable ? safeError(runtime, thread.error) : null}
      submitting={submitTurn.isPending}
      pendingMessage={pendingTurn?.message ?? null}
      processProjection={
        hasPersistedConversation ||
        currentDraft !== null ||
        currentContract !== null ||
        currentRun !== null
          ? {
              occurredAt:
                currentRun?.createdAt ??
                currentContract?.createdAt ??
                currentDraft?.createdAt ??
                threadEntries.at(-1)?.createdAt ??
                project.data.createdAt,
              node: (
                <ResearchProcessProjection
                  visible
                  run={currentRun}
                  planItems={researchPresentation.planItems}
                  events={events.data.events}
                  eventError={
                    events.data.error
                      ? safeError(runtime, events.data.error)
                      : null
                  }
                  focusPlanRequest={planFocusRequest}
                />
              ),
            }
          : null
      }
      onAnswer={(questionId, suggestedAnswer) => {
        setAnswerToQuestionId(questionId);
        if (suggestedAnswer) setMessage(suggestedAnswer);
        requestAnimationFrame(() =>
          document
            .querySelector<HTMLElement>('[data-testid="chat-input"]')
            ?.focus(),
        );
      }}
      onOpenDraft={(draftId) => {
        if (parseEntityId(draftId) !== null) setReviewOpen(true);
      }}
      onRetryLoad={() => void thread.refetch()}
    />
  );
  const inspector = (
    <ResearchInspector
      draft={currentDraft}
      contract={currentContract}
      presentation={researchPresentation}
      artifactStatus={
        artifacts.isPending
          ? "载入中"
          : `${
              artifacts.data?.filter((artifact) =>
                [
                  "analysis_report",
                  "visualization",
                  "model_evaluation",
                ].includes(artifact.kind),
              ).length ?? 0
            } 项`
      }
      artifactPanel={
        <ScientificArtifactPanel
          artifacts={artifacts.data ?? []}
          selectedVersionId={selectedArtifactVersionId}
          loading={artifacts.isPending}
          loadError={
            artifacts.isError ? safeError(runtime, artifacts.error) : null
          }
          detailLoading={
            scientificArtifact.isPending &&
            scientificArtifact.fetchStatus !== "idle"
          }
          detailError={
            scientificArtifact.isError
              ? safeError(runtime, scientificArtifact.error)
              : null
          }
          scientificArtifact={scientificArtifact.data ?? null}
          onSelect={setExplicitArtifactVersionId}
          loadContent={loadScientificContent}
        />
      }
    />
  );
  const presentationRuntime: ResearchWorkspaceRuntime = {
    project: {
      name: project.data.name,
      statusLabel: researchPresentation.statusLabel,
    },
    navigation: {
      projects: projectNavigation(
        projectList,
        projectId,
        pinned.pinnedProjects,
        researchPresentation,
      ),
      onOpenProject,
      onNewResearch: () => creation.setDialogOpen(true),
      onReturnHome: () => returnHome(runtime),
      onToggleProjectPinned: pinned.togglePinned,
      onRequestProjectRename: actions.requestRename,
      onRequestProjectDelete: actions.requestDelete,
    },
    composer: threadReady
      ? {
          submitting: submitTurn.isPending,
          value: message,
          placeholder: "描述你的研究问题、对象或预期成果",
          hasStartedConversation,
          onValueChange: setMessage,
          onSubmit: submitMessage,
          leadingActions: (
            <>
              <Button
                variant="ghost"
                size="small"
                disabled={currentDraft === null && currentContract === null}
                onClick={() => setReviewOpen(true)}
              >
                {currentContract
                  ? "研究协议 · 已确认"
                  : currentDraft
                    ? "研究协议 · 草稿"
                    : "研究协议"}
              </Button>
              <span className="truncate text-xs text-[var(--oh-muted)]">
                Enter 提交 · Shift+Enter 换行
              </span>
            </>
          ),
          beforeInput: answerToQuestionId ? (
            <div className="flex items-center justify-between px-1 text-xs text-[var(--oh-muted)]">
              <span>正在回答助手的问题</span>
              <Button
                variant="ghost"
                size="small"
                onClick={() => setAnswerToQuestionId(null)}
              >
                取消回答
              </Button>
            </div>
          ) : null,
        }
      : null,
    activation: null,
    threadPanel,
    inspectorPanel: hasPersistedConversation ? inspector : null,
  };

  return (
    <>
      <WorkspaceShell runtime={presentationRuntime} />
      <ResearchContractReviewDialog
        open={reviewOpen}
        onOpenChange={setReviewOpen}
        draft={currentDraft}
        catalog={researchCatalog.data ?? null}
        contract={currentContract}
        runStatusLabel={runId ? researchPresentation.statusLabel : null}
        pendingAction={pendingAction}
        errorMessage={errorMessage}
        onSave={async (intent, contractInput) => {
          if (!currentDraft) return;
          await updateDraft.mutateAsync({
            projectId,
            draftId: currentDraft.id,
            expectedVersion: currentDraft.version,
            input: { intent, contract: contractInput },
          });
        }}
        onConfirm={async () => {
          if (!currentDraft) return;
          await confirmContract.mutateAsync({
            projectId,
            draftId: currentDraft.id,
            expectedDraftVersion: currentDraft.version,
          });
          setReviewOpen(false);
        }}
        onCreateRun={async () => {
          if (!currentContract) return;
          await createRun.mutateAsync({
            projectId,
            contractId: currentContract.id,
            executionMode: "live",
          });
          setReviewOpen(false);
        }}
        onViewPlan={() => {
          setReviewOpen(false);
          setPlanFocusRequest((current) => current + 1);
        }}
      />
      {creation.dialog}
      {actions.dialog}
    </>
  );
}

function WorkspaceShell({
  runtime,
}: {
  readonly runtime: ResearchWorkspaceRuntime;
}) {
  return (
    <div className="workspace-host">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <div className="workspace-host__desktop">
        <OpenHandsWorkspaceRoot runtime={runtime} />
      </div>
      <Toaster closeButton />
      <section className="workspace-host__narrow" aria-label="桌面设备提示">
        <h1>请使用桌面设备</h1>
        <p>研究工作台需要至少 1024 像素宽的浏览器窗口。</p>
      </section>
    </div>
  );
}
