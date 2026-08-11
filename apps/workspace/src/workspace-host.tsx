import { useMutation, useQueries, useQuery } from "@tanstack/react-query";
import {
  CASE_KEY,
  type DomainEntityId,
  type ExecutionMode,
} from "@xingwen/domain";
import type {
  ProjectViewModel,
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
  ResearchRunViewModel,
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
import { FileSearch } from "@xingwen/ui/icons";
import { useEffect, useMemo, useState } from "react";

import {
  OpenHandsWorkspaceRoot,
  type ResearchWorkspaceRuntime,
} from "../upstream/openhands/src/root";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { ContractCheckpoint } from "./components/contract-checkpoint";
import { ProjectCreateDialog } from "./components/project-create-dialog";

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

async function exitSystem(runtime: WorkspaceRuntimeBoundaries): Promise<void> {
  try {
    await runtime.application.sessionGate.logout();
  } finally {
    globalThis.location.assign(runtime.siteUrl);
  }
}

function FirstRunContext() {
  return (
    <Empty className="workspace-context-empty">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <FileSearch aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle>从一个真实项目开始</EmptyTitle>
        <EmptyDescription>
          创建项目后，在同一工作台依次提出研究意图、确认研究协议并查看运行活动。
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function useProjectCreation({ runtime, onOpenProject }: WorkspaceEntryProps) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const createProject = useMutation(
    runtime.application.mutations.projectCreate(),
  );
  const errorMessage =
    createProject.error === null
      ? null
      : safeError(runtime, createProject.error);

  return {
    dialogOpen,
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

export function WorkspaceEntry({
  runtime,
  onOpenProject,
}: WorkspaceEntryProps) {
  const projects = useQuery(runtime.application.queries.projects());
  const creation = useProjectCreation({ runtime, onOpenProject });
  const activation = projects.isError
    ? {
        title: "研究项目载入失败",
        description: safeError(runtime, projects.error),
        actionLabel: "重试",
        onAction: () => void projects.refetch(),
      }
    : projects.isPending
      ? {
          title: "正在载入研究项目",
          description: "工作台正在恢复当前会话的项目与运行引用。",
          actionLabel: "重新载入",
          onAction: () => void projects.refetch(),
        }
      : projects.data.length === 0
        ? {
            title: "建立第一个研究项目",
            description:
              "项目会保存研究协议与运行引用。创建后即可在这里直接提出研究意图。",
            actionLabel: "新建研究项目",
            onAction: () => creation.setDialogOpen(true),
          }
        : {
            title: "继续已有研究，或开始新项目",
            description:
              "从侧栏选择项目即可恢复上下文；需要新的研究边界时，创建一个独立项目。",
            actionLabel: "新建研究项目",
            onAction: () => creation.setDialogOpen(true),
          };
  const presentationRuntime: ResearchWorkspaceRuntime = {
    project: null,
    run: null,
    navigation: {
      projects: projectNavigation(projects.data ?? [], null, new Map()),
      onOpenProject,
      onNewResearch: () => creation.setDialogOpen(true),
      onLogout: () => void exitSystem(runtime),
    },
    composer: {
      canSubmitIntent: false,
      submitting: false,
      submitIntent: null,
    },
    activation,
    activityEvents: [],
    contextPanel: <FirstRunContext />,
  };

  return (
    <>
      <WorkspaceShell runtime={presentationRuntime} />
      {creation.dialog}
    </>
  );
}

interface WorkspaceHostProps {
  readonly runtime: WorkspaceRuntimeBoundaries;
  readonly projectId: DomainEntityId;
  readonly onOpenProject: (projectId: string) => void;
}

function ContextEmpty() {
  return (
    <Empty className="workspace-context-empty">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <FileSearch aria-hidden="true" />
        </EmptyMedia>
        <EmptyTitle>等待研究意图</EmptyTitle>
        <EmptyDescription>
          在左侧 Composer 描述问题后，这里会打开结构化研究协议检查点。
        </EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}

function projectNavigation(
  projects: readonly ProjectViewModel[],
  projectId: DomainEntityId | null,
  statuses: ReadonlyMap<DomainEntityId, string>,
) {
  return projects.map((project) => ({
    id: project.id,
    title: project.name,
    status: project.latestRunId
      ? (statuses.get(project.latestRunId) ?? "已有研究运行")
      : project.activeContractId
        ? "协议已确认"
        : "等待研究意图",
    updatedAt: project.updatedAt,
    current: project.id === projectId,
  }));
}

export function WorkspaceHost({
  runtime,
  projectId,
  onOpenProject,
}: WorkspaceHostProps) {
  const [intent, setIntent] = useState("");
  const [draft, setDraft] = useState<ResearchContractDraftViewModel | null>(
    null,
  );
  const [confirmedContract, setConfirmedContract] =
    useState<ResearchContractViewModel | null>(null);
  const [createdRun, setCreatedRun] = useState<ResearchRunViewModel | null>(
    null,
  );
  const creation = useProjectCreation({ runtime, onOpenProject });

  const project = useQuery(runtime.application.queries.project(projectId));
  const projects = useQuery(runtime.application.queries.projects());
  const projectContractId = project.data?.activeContractId ?? null;
  const activeContractId =
    confirmedContract?.id ?? projectContractId ?? projectId;
  const hasActiveContract =
    confirmedContract !== null || projectContractId !== null;
  const contractQuery = useQuery({
    ...runtime.application.queries.contract(activeContractId),
    enabled: hasActiveContract && confirmedContract === null,
  });
  const contract = confirmedContract ?? contractQuery.data ?? null;
  const projectRunId = project.data?.latestRunId ?? null;
  const activeRunId = createdRun?.id ?? projectRunId ?? projectId;
  const hasActiveRun = createdRun !== null || projectRunId !== null;
  const runQuery = useQuery({
    ...runtime.application.queries.run(activeRunId),
    enabled: hasActiveRun,
  });
  const run = createdRun ?? runQuery.data ?? null;
  const runEvents = useQuery(
    runtime.application.queries.runEvents(activeRunId),
  );

  const projectRuns = useQueries({
    queries: (projects.data ?? []).flatMap((item) =>
      item.latestRunId === null
        ? []
        : [runtime.application.queries.run(item.latestRunId)],
    ),
  });
  const runStatuses = useMemo(() => {
    const result = new Map<DomainEntityId, string>();
    for (const query of projectRuns) {
      if (query.data) result.set(query.data.id, query.data.status);
    }
    return result;
  }, [projectRuns]);

  useEffect(() => {
    if (!hasActiveRun) return undefined;
    const feed = runtime.application.createRunEventFeed(activeRunId);
    feed.start();
    return () => feed.stop();
  }, [activeRunId, hasActiveRun, runtime.application]);

  const createDraft = useMutation(runtime.application.mutations.draftCreate());
  const saveDraft = useMutation(runtime.application.mutations.draftUpdate());
  const confirmContract = useMutation(
    runtime.application.mutations.contractConfirm(),
  );
  const createRun = useMutation(runtime.application.mutations.runCreate());
  const mutationError =
    createDraft.error ??
    saveDraft.error ??
    confirmContract.error ??
    createRun.error;
  const readError = contractQuery.error ?? runQuery.error ?? runEvents.error;
  const errorMessage = mutationError ? safeError(runtime, mutationError) : null;
  const pendingAction = createDraft.isPending
    ? "create-draft"
    : saveDraft.isPending
      ? "save-draft"
      : confirmContract.isPending
        ? "confirm-contract"
        : createRun.isPending
          ? "create-run"
          : null;

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
        <SpinnerWorkspace />
      </section>
    );
  }

  const contextPanel =
    intent || draft || contract || run ? (
      <ContractCheckpoint
        intent={intent}
        draft={draft}
        contract={contract}
        run={run}
        pendingAction={pendingAction}
        errorMessage={
          errorMessage ?? (readError ? safeError(runtime, readError) : null)
        }
        onCreateDraft={async (nextIntent, input) => {
          const nextDraft = await createDraft.mutateAsync({
            projectId,
            intent: nextIntent,
            contract: input,
          });
          setIntent(nextIntent);
          setDraft(nextDraft);
        }}
        onSaveDraft={async (nextIntent, input) => {
          if (!draft) return;
          const nextDraft = await saveDraft.mutateAsync({
            draftId: draft.id,
            expectedVersion: draft.version,
            input: { intent: nextIntent, contract: input },
          });
          setIntent(nextIntent);
          setDraft(nextDraft);
        }}
        onConfirmContract={async () => {
          if (!draft) return;
          const nextContract = await confirmContract.mutateAsync({
            projectId,
            draftId: draft.id,
            expectedDraftVersion: draft.version,
          });
          setConfirmedContract(nextContract);
        }}
        onCreateRun={async (executionMode: ExecutionMode) => {
          if (!contract) return;
          const nextRun = await createRun.mutateAsync({
            projectId,
            contractId: contract.id,
            executionMode,
          });
          setCreatedRun(nextRun);
        }}
      />
    ) : (
      <ContextEmpty />
    );

  const presentationRuntime: ResearchWorkspaceRuntime = {
    project: { name: project.data.name },
    run: run ? { status: run.status, executionMode: run.executionMode } : null,
    navigation: {
      projects: projectNavigation(
        projects.data ?? [project.data],
        projectId,
        runStatuses,
      ),
      onOpenProject,
      onNewResearch: () => creation.setDialogOpen(true),
      onLogout: () => void exitSystem(runtime),
    },
    composer: {
      canSubmitIntent: !intent && !draft && !contract && !run,
      submitting: false,
      submitIntent: async (nextIntent) => {
        setIntent(nextIntent.trim());
      },
    },
    activation: null,
    activityEvents: runEvents.data.events,
    contextPanel,
  };

  return (
    <>
      <WorkspaceShell runtime={presentationRuntime} />
      {creation.dialog}
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
      <section className="workspace-host__narrow" aria-label="桌面设备提示">
        <h1>请使用桌面设备</h1>
        <p>研究工作台需要至少 1024 像素宽的浏览器窗口。</p>
      </section>
    </div>
  );
}

function SpinnerWorkspace() {
  return (
    <>
      <h1>正在载入研究项目</h1>
      <Skeleton className="workspace-loading-skeleton" />
    </>
  );
}
