import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import { CASE_KEY, parseEntityId, type DomainEntityId } from "@xingwen/domain";
import {
  buildUnifiedWorkspaceStream,
  type ProjectViewModel,
  type ResearchRunViewModel,
} from "@xingwen/research-adapter";
import {
  Alert,
  AlertDescription,
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Button,
  Skeleton,
  Toaster,
  toast,
} from "@xingwen/ui";
import {
  LoaderCircle,
  RotateCcw,
  Square,
  TriangleAlert,
} from "@xingwen/ui/icons";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import {
  OpenHandsWorkspaceRoot,
  type ResearchNavigationStatus,
  type ResearchWorkspaceRuntime,
} from "../upstream/openhands/src/root";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { ProjectActionDialogs } from "./components/project-action-dialogs";
import { useArtifactPresentation } from "./components/artifact-presentation";
import { ResearchMessageStream } from "./components/research-message-stream";
import { ProtocolDraftCard } from "./components/protocol-draft-card";
import { StepProgressBar } from "./components/step-progress-bar";
import {
  DockedWorkspacePanel,
  ResearchInspectorTabs,
} from "./components/research-inspector";
import { ResearchContractReviewDialog } from "./components/research-contract-review-dialog";
import {
  deriveResearchPresentation,
  type ResearchPresentation,
  type ResearchPresentationState,
} from "./presentation/research-presentation";
import {
  lastViewedProjectId,
  type ProjectAccessLog,
  readPinnedProjects,
  readProjectAccess,
  writePinnedProjects,
  writeProjectAccess,
} from "./application/navigation-preferences";
import { useResearchWorkspaceState } from "./hooks/use-research-workspace-state";
import { useResearchWorkspaceActions } from "./hooks/use-research-workspace-actions";
import { useResearchAttachments } from "./hooks/use-research-attachments";
import { useResearchTurnSubmit } from "./application/use-research-turn-submit";

function RunLifecycleControls({
  run,
  statusLabel,
  isCancelling,
  isRetrying,
  cancelError,
  retryError,
  onCancel,
  onRetry,
}: {
  readonly run: ResearchRunViewModel | null;
  readonly statusLabel: string;
  readonly isCancelling: boolean;
  readonly isRetrying: boolean;
  readonly cancelError: string | null;
  readonly retryError: string | null;
  readonly onCancel: () => Promise<void>;
  readonly onRetry: () => Promise<void>;
}) {
  const [cancelOpen, setCancelOpen] = useState(false);
  if (run === null) return null;

  const isWaiting = run.status === "waiting_for_input";
  const isFailed = run.status === "failed";
  const isActive = !run.isTerminal;
  if (!isActive && !isFailed) return null;

  const handleCancel = async () => {
    await onCancel();
    setCancelOpen(false);
  };

  return (
    <div
      className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-[var(--oh-radius-sm)] border border-[var(--oh-border)] bg-[var(--oh-surface-raised)] px-3 py-2 text-xs"
      data-testid="run-lifecycle-controls"
      role="status"
      aria-live="polite"
    >
      <div className="flex min-w-0 items-center gap-2 text-[var(--oh-muted)]">
        {isFailed ? (
          <TriangleAlert
            className="size-3.5 text-[var(--oh-warning)]"
            aria-hidden="true"
          />
        ) : (
          <LoaderCircle
            className="size-3.5 animate-spin motion-reduce:animate-none"
            aria-hidden="true"
          />
        )}
        <span className="truncate">
          {isFailed ? "研究遇到问题" : statusLabel}
        </span>
        {cancelError || retryError ? (
          <span className="truncate text-[var(--oh-warning)]">
            {cancelError ?? retryError}
          </span>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-1.5">
        {isFailed ? (
          <Button
            variant="secondary"
            size="small"
            disabled={isRetrying}
            onClick={() => void onRetry()}
            className="gap-1.5"
          >
            <RotateCcw className="size-3.5" aria-hidden="true" />
            {isRetrying ? "正在重试" : "重试研究"}
          </Button>
        ) : (
          <>
            {isWaiting ? (
              <span className="text-[var(--oh-muted)]">等待你的回答</span>
            ) : null}
            <AlertDialog open={cancelOpen} onOpenChange={setCancelOpen}>
              <Button
                variant="ghost"
                size="small"
                disabled={isCancelling}
                onClick={() => setCancelOpen(true)}
                className="gap-1.5 text-[var(--oh-muted)] hover:text-foreground"
              >
                <Square className="size-3.5" aria-hidden="true" />
                {isCancelling ? "正在停止" : "停止研究"}
              </Button>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>停止当前研究？</AlertDialogTitle>
                  <AlertDialogDescription>
                    已发布的研究结果会保留，尚未完成的工作将停止。
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>继续研究</AlertDialogCancel>
                  <AlertDialogAction
                    disabled={isCancelling}
                    onClick={(event) => {
                      event.preventDefault();
                      void handleCancel();
                    }}
                  >
                    停止研究
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </>
        )}
      </div>
    </div>
  );
}

interface WorkspaceEntryProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly missingNotice?: boolean;
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

const EMPTY_PROJECTS: readonly ProjectViewModel[] = Object.freeze([]);

/** Track recent project access and the last viewed project (UI navigation preference). */
function useProjectAccess() {
  const [accessLog, setAccessLog] =
    useState<ProjectAccessLog>(readProjectAccess);
  const recordAccess = useCallback((projectId: string) => {
    setAccessLog((current) => {
      const next = {
        ...current,
        [projectId]: new Date().toISOString(),
      };
      writeProjectAccess(next);
      return next;
    });
  }, []);
  return {
    accessLog,
    recordAccess,
    lastViewedProjectId: lastViewedProjectId(),
  };
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

/** Typed navigation status derived from server presentation state, never from display strings. */
function navigationStatus(
  state: ResearchPresentationState,
): ResearchNavigationStatus {
  switch (state) {
    case "queued":
    case "planning":
    case "fetching_data":
    case "cleaning_data":
    case "acquiring_observations":
    case "analyzing_data":
    case "training_models":
    case "building_visualizations":
    case "searching_papers":
    case "summarizing_papers":
    case "reasoning_literature":
    case "building_graph":
    case "assistant_processing":
      return "running";
    case "waiting_for_input":
    case "awaiting_clarification":
      return "waiting";
    case "failed":
    case "cancelled":
    case "assistant_unavailable":
      return "error";
    default:
      return "idle";
  }
}

function useProjectCreation({ runtime, onOpenProject }: WorkspaceEntryProps) {
  const createProject = useMutation(
    runtime.application.mutations.projectCreate(),
  );
  const ensuredProjectId = useRef<DomainEntityId | null>(null);
  const inFlightEnsure = useRef<Promise<DomainEntityId> | null>(null);

  const createProjectRecord = useCallback(async () => {
    const project = await createProject.mutateAsync({
      name: "新建研究",
      description: "",
      caseKey: CASE_KEY,
    });
    return project.id;
  }, [createProject]);

  const ensureProject = useCallback(async (): Promise<DomainEntityId> => {
    if (ensuredProjectId.current) return ensuredProjectId.current;
    if (inFlightEnsure.current) return inFlightEnsure.current;
    const pending = createProjectRecord()
      .then((projectId) => {
        ensuredProjectId.current = projectId;
        return projectId;
      })
      .finally(() => {
        inFlightEnsure.current = null;
      });
    inFlightEnsure.current = pending;
    return pending;
  }, [createProjectRecord]);

  return {
    pending: createProject.isPending,
    ensureProject,
    create: async () => {
      try {
        const projectId = await createProjectRecord();
        onOpenProject(projectId);
      } catch (error) {
        toast.error("新建研究失败", {
          description: safeError(runtime, error),
        });
      }
    },
  };
}

/**
 * The empty workspace entry: one explicit send creates the Project and
 * submits the message as its first research turn, then opens the Project.
 */
function useResearchEntry({
  runtime,
  onOpenProject,
  creation,
}: WorkspaceEntryProps & {
  readonly creation: ReturnType<typeof useProjectCreation>;
}) {
  const [message, setMessage] = useState("");
  const attachments = useResearchAttachments({
    runtime,
    projectId: null,
    ensureProject: creation.ensureProject,
    onProjectReady: onOpenProject,
  });
  const { submitMessage, isSubmitting } = useResearchTurnSubmit({
    runtime,
    resolveProjectId: creation.ensureProject,
    setMessage,
    onProjectReady: onOpenProject,
  });
  const startFromMessage = async (nextMessage: string) => {
    if (creation.pending || isSubmitting) return;
    try {
      await submitMessage(nextMessage, null);
    } catch {
      // The shared Composer seam restores the draft and reports the error.
    }
  };
  return {
    composer: {
      submitting: creation.pending || isSubmitting,
      value: message,
      onValueChange: setMessage,
      onSubmit: (value: string) => void startFromMessage(value),
      ...attachments,
    },
    startFromMessage,
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
  accessLog: ProjectAccessLog,
  currentPresentation?: ResearchPresentation,
) {
  const pinned = new Set(pinnedProjects);
  return [...projects]
    .sort((left, right) => {
      const pinnedOrder =
        Number(pinned.has(right.id)) - Number(pinned.has(left.id));
      const leftAccess = accessLog[left.id] ?? "";
      const rightAccess = accessLog[right.id] ?? "";
      return pinnedOrder || rightAccess.localeCompare(leftAccess);
    })
    .map((project) => {
      const presentation =
        project.id === projectId && currentPresentation
          ? currentPresentation
          : deriveResearchPresentation({ project });
      return {
        id: project.id,
        title: project.name,
        status: navigationStatus(presentation.state),
        current: project.id === projectId,
        pinned: pinned.has(project.id),
        lastAccessedAt: accessLog[project.id] ?? project.updatedAt,
      };
    });
}

function ResearchComposerLeadingActions({
  attachmentAction,
  protocolDisabled,
  protocolLabel,
  onOpenProtocolEditor,
}: {
  readonly attachmentAction: ReactNode;
  readonly protocolDisabled: boolean;
  readonly protocolLabel: string;
  readonly onOpenProtocolEditor: () => void;
}) {
  return (
    <div className="flex min-w-0 items-center gap-[var(--oh-space-2)]">
      {attachmentAction}
      <Button
        variant="ghost"
        size="small"
        disabled={protocolDisabled}
        onClick={onOpenProtocolEditor}
        className="gap-1 text-xs text-[var(--oh-muted)]"
      >
        {protocolLabel}
      </Button>
    </div>
  );
}

function runtimeForEntry(
  entryComposer: {
    readonly submitting: boolean;
    readonly value: string;
    readonly onValueChange: (value: string) => void;
    readonly onSubmit: (message: string) => void;
    readonly attachmentAction: ReactNode;
    readonly attachmentStrip: ReactNode;
    readonly dragActive: boolean;
    readonly handleFilesSelected: (files: readonly File[]) => void;
    readonly handlePasteFiles: (files: readonly File[]) => void;
    readonly handleDropFiles: (files: readonly File[]) => void;
    readonly handleDragOver: () => void;
    readonly handleDragLeave: () => void;
  },
  runtime: WorkspaceRuntimeBoundaries,
  projects: readonly ProjectViewModel[],
  pinnedProjects: readonly string[],
  accessLog: ProjectAccessLog,
  onOpenProject: (projectId: string) => void,
  onNewResearch: () => void,
  onToggleProjectPinned: (projectId: string) => void,
  onRequestProjectRename: (projectId: string) => void,
  onRequestProjectDelete: (projectId: string) => void,
): ResearchWorkspaceRuntime {
  return {
    project: null,
    navigation: {
      projects: projectNavigation(projects, null, pinnedProjects, accessLog),
      onOpenProject,
      onNewResearch,
      onReturnHome: () => returnHome(runtime),
      onToggleProjectPinned,
      onRequestProjectRename,
      onRequestProjectDelete,
    },
    // The empty workspace is itself the research entry: one explicit send
    // creates the Project and submits the first research turn.
    composer: {
      submitting: entryComposer.submitting,
      value: entryComposer.value,
      placeholder: "输入研究目标、对象或约束，开始研究",
      hasStartedConversation: false,
      leadingActions: (
        <ResearchComposerLeadingActions
          attachmentAction={entryComposer.attachmentAction}
          protocolDisabled
          onOpenProtocolEditor={() => undefined}
          protocolLabel="研究协议"
        />
      ),
      beforeInput: entryComposer.attachmentStrip,
      onFilesSelected: entryComposer.handleFilesSelected,
      onDragOver: entryComposer.handleDragOver,
      onDragLeave: entryComposer.handleDragLeave,
      onDropFiles: entryComposer.handleDropFiles,
      dragActive: entryComposer.dragActive,
      onValueChange: entryComposer.onValueChange,
      onSubmit: async (message) => entryComposer.onSubmit(message),
    },
    threadPanel: <div className="research-thread-entry-placeholder" />,
    threadItemCount: 0,
    inspectorPanel: null,
  };
}

export function WorkspaceEntry({
  runtime,
  missingNotice = false,
  onOpenProject,
}: WorkspaceEntryProps) {
  const projects = useQuery(runtime.application.queries.projects());
  const creation = useProjectCreation({ runtime, onOpenProject });
  const entry = useResearchEntry({ runtime, onOpenProject, creation });
  const projectList = projects.data ?? EMPTY_PROJECTS;
  const pinned = usePinnedProjects(projectList);
  const access = useProjectAccess();
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
        entry.composer,
        runtime,
        projectList,
        pinned.pinnedProjects,
        access.accessLog,
        onOpenProject,
        () => void creation.create(),
        pinned.togglePinned,
        actions.requestRename,
        actions.requestDelete,
      )}
    />
  );
  return (
    <>
      {missingNotice ? (
        <p
          className="px-4 py-2 text-sm text-[var(--oh-muted)]"
          data-testid="missing-project-notice"
          role="status"
        >
          这个研究已不存在。
        </p>
      ) : null}
      {content}
      {actions.dialog}
    </>
  );
}

interface WorkspaceHostProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly artifactVersionId: DomainEntityId | null;
  readonly onOpenProject: (projectId: string) => void;
  readonly onOpenArtifactVersion: (artifactVersionId: DomainEntityId) => void;
  readonly onReturnToOverview: () => void;
  readonly onProjectDeleted: () => void;
}

export function WorkspaceHost({
  runtime,
  projectId,
  artifactVersionId,
  onOpenProject,
  onOpenArtifactVersion,
  onReturnToOverview,
  onProjectDeleted,
}: WorkspaceHostProps) {
  const {
    dockedTab,
    setDockedTab,
    reviewOpen,
    setReviewOpen,
    message,
    setMessage,
    answerToQuestionId,
    setAnswerToQuestionId,
    pendingTurn,
    setPendingTurn,
  } = useResearchWorkspaceState();

  const [inspectorRequestOverride, setInspectorRequestOverride] = useState<{
    readonly key: string;
  } | null>(null);

  const access = useProjectAccess();
  useEffect(() => {
    access.recordAccess(projectId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

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

  const checkpoint = useQuery({
    ...runtime.application.queries.checkpoint(
      projectId,
      runId as DomainEntityId,
    ),
    enabled: runId !== null,
  });
  const checkpointDecision = useMutation(
    runtime.application.mutations.checkpointDecisionSubmit(),
  );
  const cancelRun = useMutation(runtime.application.mutations.runCancel());
  const retryRun = useMutation(runtime.application.mutations.runRetry());

  const events = useQuery({
    ...runtime.application.queries.runEvents(
      projectId,
      runId as DomainEntityId,
    ),
    enabled: false,
  });

  const artifacts = useQuery({
    ...runtime.application.queries.artifactsByRun(
      projectId,
      runId ?? projectId,
    ),
    enabled: runId !== null,
  });

  const attachments = useResearchAttachments({
    runtime,
    projectId,
    draftId: activeDraftId,
    runId,
  });

  useEffect(() => {
    if (runId === null) return undefined;
    const feed = runtime.application.createRunEventFeed(projectId, runId);
    feed.start();
    return () => feed.stop();
  }, [projectId, runId, runtime.application]);

  const thread = useQuery(runtime.application.queries.thread(projectId));

  const currentDraft = draft.data ?? null;
  const currentContract = contract.data ?? null;
  const currentRun = run.data ?? null;
  const stepsData = steps.data ?? [];
  const threadEntries = thread.data ?? [];
  const artifactList = artifacts.data ?? [];

  // Real server version→Artifact metadata; the stream never guesses the
  // relationship by comparing Artifact ids with ArtifactVersion ids.
  const versionQueries = useQueries({
    queries: artifactList.map((artifact) =>
      runtime.application.queries.artifactVersions(projectId, artifact.id),
    ),
  });
  const artifactVersionLinks = new Map<string, string>();
  artifactList.forEach((artifact, index) => {
    const versions = versionQueries[index]?.data;
    if (!versions) return;
    for (const version of versions) {
      artifactVersionLinks.set(version.id, artifact.id);
    }
  });

  const {
    submitMessage,
    confirmAndRun,
    retryRunStart,
    isSubmitting,
    isConfirming,
    updateDraft,
    createRun,
  } = useResearchWorkspaceActions({
    runtime,
    projectId,
    currentDraft,
    currentContract,
    setPendingTurn,
    setMessage,
    setAnswerToQuestionId,
  });

  const researchPresentation = project.data
    ? deriveResearchPresentation({
        project: project.data,
        entries: threadEntries,
        draft: currentDraft,
        contract: currentContract,
        run: currentRun,
        steps: stepsData,
        pendingActionId: pendingTurn?.actionId ?? null,
      })
    : null;

  const error = updateDraft.error ?? thread.error;
  const errorMessage = error ? safeError(runtime, error) : null;
  const pendingAction = updateDraft.isPending
    ? "save-draft"
    : isConfirming
      ? "confirm-contract"
      : null;

  const runStartFailed =
    currentContract !== null && runId === null && createRun.error !== null;

  const artifactPresentation = useArtifactPresentation({
    runtime,
    projectId,
    runId,
    artifactVersionId,
    onOpenArtifactVersion,
    onReturnToOverview,
  });
  const isArtifactFullscreen = artifactVersionId !== null;

  const dockedWorkspace = researchPresentation ? (
    <DockedWorkspacePanel
      activeTab={dockedTab}
      onTabChange={setDockedTab}
      draft={currentDraft}
      contract={currentContract}
      presentation={researchPresentation}
      resultPanel={artifactPresentation.resultPanel}
    />
  ) : null;

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
  if (researchPresentation === null) {
    throw new Error("Loaded project is missing its research presentation.");
  }

  // Synthesize Unified Stream Items
  const streamItems = buildUnifiedWorkspaceStream({
    project: project.data,
    entries: threadEntries,
    draft: currentDraft,
    contract: currentContract,
    run: currentRun,
    steps: stepsData,
    events: events.data?.events ?? [],
    artifacts: artifactList,
    artifactVersionLinks,
    checkpoint: checkpoint.data ?? null,
    pendingUserMessage: pendingTurn?.message,
  });

  const threadReady = thread.data !== undefined;
  const hasPersistedConversation = threadEntries.length > 0;
  const hasStartedConversation =
    hasPersistedConversation ||
    currentDraft !== null ||
    currentContract !== null ||
    currentRun !== null ||
    stepsData.length > 0 ||
    streamItems.length > 0 ||
    artifactPresentation.hasArtifacts ||
    pendingTurn !== null;

  const handleOpenProtocolEditor = () => {
    setReviewOpen(true);
    const inputField = document.querySelector<HTMLElement>(
      '[data-testid="chat-input"]',
    );
    inputField?.blur();
  };

  const handleRefineInChat = () => {
    document.querySelector<HTMLElement>('[data-testid="chat-input"]')?.focus();
  };

  const handleViewPlan = () => {
    setDockedTab("overview");
    setInspectorRequestOverride({
      key: `overview:${Date.now()}`,
    });
  };

  const handleAnswerQuestion = (
    questionId: string,
    suggestedAnswer?: string,
  ) => {
    setAnswerToQuestionId(questionId);
    if (suggestedAnswer) setMessage(suggestedAnswer);
    requestAnimationFrame(() => {
      document
        .querySelector<HTMLElement>('[data-testid="chat-input"]')
        ?.focus();
    });
  };

  const threadPanel = (
    <div className="flex min-w-0 flex-col">
      <RunLifecycleControls
        run={currentRun}
        statusLabel={researchPresentation.statusLabel}
        isCancelling={cancelRun.isPending}
        isRetrying={retryRun.isPending}
        cancelError={
          cancelRun.error ? safeError(runtime, cancelRun.error) : null
        }
        retryError={retryRun.error ? safeError(runtime, retryRun.error) : null}
        onCancel={async () => {
          if (runId === null) return;
          await cancelRun.mutateAsync({ projectId, runId });
        }}
        onRetry={async () => {
          if (runId === null) return;
          await retryRun.mutateAsync({ projectId, runId });
        }}
      />
      <ResearchMessageStream
        items={streamItems}
        onOpenArtifactVersion={onOpenArtifactVersion}
        onConfirmProtocol={confirmAndRun}
        onCheckpointDecision={async (runIdOfCheckpoint, decision) => {
          await checkpointDecision.mutateAsync({
            projectId,
            runId: parseEntityId(runIdOfCheckpoint) as DomainEntityId,
            decision,
          });
        }}
        isSubmittingCheckpoint={checkpointDecision.isPending}
        onOpenProtocolEditor={handleOpenProtocolEditor}
        onRefineInChat={handleRefineInChat}
        onViewPlan={handleViewPlan}
        isConfirmingProtocol={isConfirming}
        onAnswerQuestion={handleAnswerQuestion}
        renderProtocolDraft={(props) => <ProtocolDraftCard {...props} />}
        renderStepProgress={(props) => <StepProgressBar {...props} />}
      />
    </div>
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
        access.accessLog,
        researchPresentation,
      ),
      onOpenProject,
      onNewResearch: () => void creation.create(),
      onReturnHome: () => returnHome(runtime),
      onToggleProjectPinned: pinned.togglePinned,
      onRequestProjectRename: actions.requestRename,
      onRequestProjectDelete: actions.requestDelete,
    },
    composer: threadReady
      ? {
          submitting: isSubmitting,
          value: message,
          placeholder:
            "随心输入研究意图、对象或约束（Enter 提交 · Shift+Enter 换行）",
          hasStartedConversation,
          onValueChange: setMessage,
          onSubmit: (nextMsg) => submitMessage(nextMsg, answerToQuestionId),
          leadingActions: (
            <ResearchComposerLeadingActions
              attachmentAction={attachments.attachmentAction}
              protocolDisabled={
                currentDraft === null && currentContract === null
              }
              onOpenProtocolEditor={handleOpenProtocolEditor}
              protocolLabel={
                currentContract
                  ? "研究协议 · 已确认"
                  : currentDraft
                    ? "研究协议 · 草稿"
                    : "研究协议"
              }
            />
          ),
          beforeInput: (
            <>
              {attachments.attachmentStrip}
              {runStartFailed && currentContract ? (
                <div
                  className="mb-2 flex items-center justify-between gap-2 rounded-[var(--oh-radius-sm)] border border-[var(--oh-border)] bg-[var(--oh-surface-raised)] px-3 py-2 text-sm"
                  data-testid="run-start-failed"
                  role="status"
                >
                  <span>研究协议已经确认，但研究启动失败。</span>
                  <Button
                    variant="secondary"
                    size="small"
                    disabled={createRun.isPending}
                    onClick={() => void retryRunStart()}
                  >
                    重新启动研究
                  </Button>
                </div>
              ) : null}
              {answerToQuestionId ? (
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
              ) : null}
            </>
          ),
          onFilesSelected: attachments.handleFilesSelected,
          onDragOver: attachments.handleDragOver,
          onDragLeave: attachments.handleDragLeave,
          onDropFiles: attachments.handleDropFiles,
          dragActive: attachments.dragActive,
        }
      : null,
    threadPanel,
    threadItemCount: streamItems.length,
    inspectorPanel:
      !isArtifactFullscreen &&
      (hasPersistedConversation ||
        currentDraft !== null ||
        currentContract !== null ||
        currentRun !== null ||
        stepsData.length > 0 ||
        streamItems.length > 0 ||
        artifactPresentation.hasArtifacts)
        ? dockedWorkspace
        : null,
    inspectorDockedPanel: isArtifactFullscreen ? null : dockedWorkspace,
    inspectorDockedToolbar:
      !isArtifactFullscreen && dockedWorkspace ? (
        <ResearchInspectorTabs
          activeTab={dockedTab}
          onTabChange={setDockedTab}
          resultCount={artifactPresentation.artifactCount}
        />
      ) : null,
    inspectorDockedLabel: undefined,
    inspectorRequest:
      inspectorRequestOverride ?? artifactPresentation.inspectorRequest,
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
        onConfirmAndRun={async () => {
          await confirmAndRun();
          setReviewOpen(false);
        }}
        onViewPlan={() => {
          setReviewOpen(false);
          handleViewPlan();
        }}
      />
      {artifactPresentation.fullscreenDialog}
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
    <div className="workspace-host h-full w-full overflow-hidden bg-background">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <div className="workspace-host__desktop h-full w-full">
        <OpenHandsWorkspaceRoot runtime={runtime} />
      </div>
      <Toaster closeButton />
    </div>
  );
}
