import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
  useRouter,
} from "@tanstack/react-router";
import { parseEntityId, type DomainEntityId } from "@xingwen/domain";
import { Button, Link, Spinner } from "@xingwen/ui";
import type {
  ErrorComponentProps,
  RouterHistory,
} from "@tanstack/react-router";
import type { PublicApplicationError } from "@xingwen/research-adapter";

import { lastViewedProjectId } from "./application/navigation-preferences";
import { SessionGateRequiredError } from "./application/session-gate";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { SharePage } from "./share-page";
import { WorkspaceEntry, WorkspaceHost } from "./workspace-host";

class PrivateRouteError extends Error {
  readonly publicError: PublicApplicationError;

  constructor(publicError: PublicApplicationError) {
    super(publicError.safeMessage);
    this.name = "PrivateRouteError";
    this.publicError = publicError;
  }
}

interface WorkspaceProjectSearch {
  readonly artifactVersionId?: DomainEntityId;
}

interface WorkspaceIndexSearch {
  readonly missingProject?: true;
}

export function validateWorkspaceIndexSearch(
  search: Record<string, unknown>,
): WorkspaceIndexSearch {
  const candidate = search["missingProject"];
  if (candidate === undefined) return {};
  if (candidate === true || candidate === "1" || candidate === 1) {
    return { missingProject: true };
  }
  return {};
}

export function validateWorkspaceProjectSearch(
  search: Record<string, unknown>,
): WorkspaceProjectSearch {
  const candidate = search["artifactVersionId"];
  if (candidate === undefined) return {};
  if (typeof candidate !== "string") {
    throw new PrivateRouteError({
      kind: "validation",
      safeMessage: "产物版本标识无效",
    });
  }
  const artifactVersionId = parseEntityId(candidate);
  if (artifactVersionId === null) {
    throw new PrivateRouteError({
      kind: "validation",
      safeMessage: "产物版本标识无效",
    });
  }
  return { artifactVersionId };
}

function RootLayout() {
  return <Outlet />;
}

function ShareRoute() {
  const { shareToken } = shareRoute.useParams();
  return <SharePage key={shareToken} shareToken={shareToken} />;
}

function WorkspaceIndexRoute() {
  const runtime = workspaceIndexRoute.useRouteContext();
  const navigate = workspaceIndexRoute.useNavigate();
  const { missingProject } = workspaceIndexRoute.useSearch();
  return (
    <WorkspaceEntry
      runtime={runtime}
      missingNotice={missingProject === true}
      onOpenProject={(projectId) =>
        void navigate({
          to: "/workspace/$projectId",
          params: { projectId },
        })
      }
    />
  );
}

function WorkspaceProjectRoute() {
  const runtime = workspaceProjectRoute.useRouteContext();
  const { projectId } = workspaceProjectRoute.useParams();
  const { artifactVersionId } = workspaceProjectRoute.useSearch();
  const navigate = workspaceProjectRoute.useNavigate();
  const parsedProjectId = parseEntityId(projectId);
  if (parsedProjectId === null) {
    throw new PrivateRouteError({
      kind: "validation",
      safeMessage: "项目标识无效",
    });
  }
  return (
    <WorkspaceHost
      key={parsedProjectId}
      runtime={runtime}
      projectId={parsedProjectId}
      artifactVersionId={artifactVersionId ?? null}
      onOpenProject={(nextProjectId) =>
        void navigate({
          to: "/workspace/$projectId",
          params: { projectId: nextProjectId },
          search: {},
        })
      }
      onOpenArtifactVersion={(nextArtifactVersionId) =>
        void navigate({
          search: { artifactVersionId: nextArtifactVersionId },
        })
      }
      onReturnToOverview={() => void navigate({ search: {} })}
      onProjectDeleted={() => void navigate({ to: "/workspace" })}
    />
  );
}

function LoadingPage() {
  return (
    <section className="route-content" aria-busy="true" aria-live="polite">
      <h1>正在载入</h1>
      <div className="route-loading" role="status">
        <Spinner aria-hidden="true" />
        <span>正在载入工作台</span>
      </div>
    </section>
  );
}

function RouteErrorPage({ error, reset }: ErrorComponentProps) {
  const publicError =
    error instanceof SessionGateRequiredError ||
    error instanceof PrivateRouteError
      ? error.publicError
      : null;
  const router = useRouter();
  const runtime = router.options.context as
    WorkspaceRuntimeBoundaries | undefined;
  const sessionRequired = publicError?.kind === "session_required";

  return (
    <section className="route-content" role="alert">
      <h1>{sessionRequired ? "需要重新建立会话" : "页面载入失败"}</h1>
      <p>
        {publicError?.safeMessage ?? "请重试；若问题持续，请返回工作台入口。"}
      </p>
      <Button
        variant="secondary"
        onClick={() => {
          if (sessionRequired) runtime?.application.sessionGate.allowReentry();
          reset();
        }}
      >
        {sessionRequired ? "重新进入工作台" : "重试"}
      </Button>
    </section>
  );
}

function NotFoundPage() {
  return (
    <section className="route-content">
      <h1>页面未找到</h1>
      <p>请求的工作台入口不存在。</p>
      <Link href="/workspace">返回研究项目</Link>
    </section>
  );
}

const rootRoute = createRootRouteWithContext<WorkspaceRuntimeBoundaries>()({
  component: RootLayout,
  errorComponent: RouteErrorPage,
  notFoundComponent: NotFoundPage,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  beforeLoad: () => {
    throw redirect({ to: "/workspace", replace: true });
  },
});

const privateWorkspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  id: "private-workspace",
  beforeLoad: async ({ context }) => {
    await context.application.sessionGate.requireSession();
  },
  component: Outlet,
});

const workspaceIndexRoute = createRoute({
  getParentRoute: () => privateWorkspaceRoute,
  path: "/workspace",
  validateSearch: validateWorkspaceIndexSearch,
  beforeLoad: async ({ context, search }) => {
    // Restore the last viewed Project as a UI navigation preference; a stale
    // or inaccessible id simply leaves the neutral workspace in place.
    if (search.missingProject === true) return;
    const restoreId = lastViewedProjectId();
    if (restoreId === null) return;
    const projectId = parseEntityId(restoreId);
    if (projectId === null) return;
    try {
      await context.queryClient.ensureQueryData(
        context.application.queries.project(projectId),
      );
    } catch {
      return;
    }
    throw redirect({
      to: "/workspace/$projectId",
      params: { projectId },
      replace: true,
    });
  },
  component: WorkspaceIndexRoute,
});

const workspaceProjectRoute = createRoute({
  getParentRoute: () => privateWorkspaceRoute,
  path: "/workspace/$projectId",
  validateSearch: validateWorkspaceProjectSearch,
  beforeLoad: async ({ context, params }) => {
    const projectId = parseEntityId(params.projectId);
    if (projectId === null) {
      throw new PrivateRouteError({
        kind: "validation",
        safeMessage: "项目标识无效",
      });
    }
    try {
      await context.queryClient.ensureQueryData(
        context.application.queries.project(projectId),
      );
    } catch (error) {
      const publicError =
        context.researchAdapter.toPublicApplicationError(error);
      if (publicError.kind === "not_found") {
        // A normal deleted/missing Project is not a technical Route error:
        // replace to the neutral workspace with a light human message.
        throw redirect({
          to: "/workspace",
          search: { missingProject: true },
          replace: true,
        });
      }
      throw new PrivateRouteError(publicError);
    }
  },
  component: WorkspaceProjectRoute,
});

const shareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/share/$shareToken",
  component: ShareRoute,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  privateWorkspaceRoute.addChildren([
    workspaceIndexRoute,
    workspaceProjectRoute,
  ]),
  shareRoute,
]);

export function createAppRouter(
  boundaries: WorkspaceRuntimeBoundaries,
  history?: RouterHistory,
) {
  const router = createRouter({
    routeTree,
    history,
    context: boundaries,
    defaultErrorComponent: RouteErrorPage,
    defaultNotFoundComponent: NotFoundPage,
    defaultPendingComponent: LoadingPage,
    defaultPendingMinMs: 150,
    defaultPreload: "intent",
  });
  boundaries.application.sessionGate.bindRouterInvalidation(() =>
    router.invalidate(),
  );
  return router;
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
