import {
  Link,
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
  redirect,
} from "@tanstack/react-router";
import type {
  ErrorComponentProps,
  RouterHistory,
} from "@tanstack/react-router";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { SharePage } from "./share-page";
import { WorkspaceHost } from "./workspace-host";

interface WorkspaceSearch {
  readonly projectId?: string;
  readonly draftId?: string;
  readonly contractId?: string;
  readonly runId?: string;
}

const IDENTIFIER_KEYS = [
  "projectId",
  "draftId",
  "contractId",
  "runId",
] as const;

function isValidIdentifier(value: unknown): value is string {
  return (
    typeof value === "string" && value.trim().length > 0 && value.length <= 128
  );
}

function optionalIdentifier(
  search: Record<string, unknown>,
  key: string,
): string | undefined {
  const value = search[key];
  if (value === undefined) return undefined;
  if (!isValidIdentifier(value)) {
    throw new Error(`Invalid ${key} search parameter.`);
  }
  return value;
}

function hasValidIdentifiers(search: Record<string, unknown>): boolean {
  return IDENTIFIER_KEYS.every(
    (key) => search[key] === undefined || isValidIdentifier(search[key]),
  );
}

function validateWorkspaceSearch(
  search: Record<string, unknown>,
): WorkspaceSearch {
  return {
    projectId: optionalIdentifier(search, "projectId"),
    draftId: optionalIdentifier(search, "draftId"),
    contractId: optionalIdentifier(search, "contractId"),
    runId: optionalIdentifier(search, "runId"),
  };
}

function RootLayout() {
  return <Outlet />;
}

function ShareRoute() {
  const { shareToken } = shareRoute.useParams();
  return <SharePage key={shareToken} shareToken={shareToken} />;
}

function LoadingPage() {
  return (
    <section className="route-content" aria-busy="true" aria-live="polite">
      <h1>正在载入</h1>
    </section>
  );
}

function RouteErrorPage({ reset }: ErrorComponentProps) {
  return (
    <section className="route-content" role="alert">
      <h1>页面载入失败</h1>
      <p>请重试；若问题持续，请返回工作台入口。</p>
      <button type="button" onClick={reset}>
        重试
      </button>
    </section>
  );
}

function NotFoundPage() {
  return (
    <section className="route-content">
      <h1>页面未找到</h1>
      <p>请求的工作台入口不存在。</p>
      <Link className="text-link" to="/">
        返回工作台入口
      </Link>
    </section>
  );
}

function TourCompatBoundary() {
  return (
    <section className="route-content" role="alert">
      <h1>页面载入失败</h1>
      <p>请重试；若问题持续，请返回工作台入口。</p>
      <Link className="text-link" to="/workspace">
        返回工作台入口
      </Link>
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

const tourRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tour",
  beforeLoad: ({ search }) => {
    const record = search as Record<string, unknown>;
    // Reject invalid identifiers without throwing so the compat boundary
    // renders cleanly: nothing is forwarded and no console error is logged.
    if (!hasValidIdentifiers(record)) return;
    throw redirect({
      to: "/workspace",
      replace: true,
      search: {
        projectId: optionalIdentifier(record, "projectId"),
        draftId: optionalIdentifier(record, "draftId"),
        contractId: optionalIdentifier(record, "contractId"),
        runId: optionalIdentifier(record, "runId"),
      },
    });
  },
  component: TourCompatBoundary,
});

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workspace",
  validateSearch: validateWorkspaceSearch,
  component: WorkspaceHost,
});

const shareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/share/$shareToken",
  component: ShareRoute,
});

const routeTree = rootRoute.addChildren([
  indexRoute,
  tourRoute,
  workspaceRoute,
  shareRoute,
]);

export function createAppRouter(
  boundaries: WorkspaceRuntimeBoundaries,
  history?: RouterHistory,
) {
  return createRouter({
    routeTree,
    history,
    context: boundaries,
    defaultErrorComponent: RouteErrorPage,
    defaultNotFoundComponent: NotFoundPage,
    defaultPendingComponent: LoadingPage,
    defaultPendingMinMs: 150,
    defaultPreload: "intent",
  });
}

export type AppRouter = ReturnType<typeof createAppRouter>;

declare module "@tanstack/react-router" {
  interface Register {
    router: AppRouter;
  }
}
