import {
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";
import { asEntityId } from "@xingwen/domain";
import { Button, Link, Spinner } from "@xingwen/ui";
import type {
  ErrorComponentProps,
  RouterHistory,
} from "@tanstack/react-router";
import type { PublicApplicationError } from "@xingwen/research-adapter";

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
  return (
    <WorkspaceEntry
      runtime={runtime}
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
  const navigate = workspaceProjectRoute.useNavigate();
  return (
    <WorkspaceHost
      runtime={runtime}
      projectId={asEntityId(projectId)}
      onOpenProject={(nextProjectId) =>
        void navigate({
          to: "/workspace/$projectId",
          params: { projectId: nextProjectId },
        })
      }
    />
  );
}

function LoadingPage() {
  return (
    <section className="route-content" aria-busy="true" aria-live="polite">
      <h1>正在载入</h1>
      <Spinner label="正在载入工作台" />
    </section>
  );
}

function RouteErrorPage({ error, reset }: ErrorComponentProps) {
  const publicError =
    error instanceof SessionGateRequiredError ||
    error instanceof PrivateRouteError
      ? error.publicError
      : null;
  const runtime = rootRoute.useRouteContext();
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
          if (sessionRequired) runtime.application.sessionGate.allowReentry();
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
  component: WorkspaceIndexRoute,
});

const workspaceProjectRoute = createRoute({
  getParentRoute: () => privateWorkspaceRoute,
  path: "/workspace/$projectId",
  beforeLoad: async ({ context, params }) => {
    const projectId = asEntityId(params.projectId);
    try {
      await context.queryClient.ensureQueryData(
        context.application.queries.project(projectId),
      );
    } catch (error) {
      throw new PrivateRouteError(
        context.researchAdapter.toPublicApplicationError(error),
      );
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
