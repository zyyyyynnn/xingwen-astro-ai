import {
  Link,
  Outlet,
  createRootRouteWithContext,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import type {
  ErrorComponentProps,
  RouterHistory,
} from "@tanstack/react-router";

import type { WorkspaceRuntimeBoundaries } from "./boundaries";
import { EntryPage } from "./pages/entry-page";
import { SharePage } from "./pages/share-page";
import { TourPage } from "./pages/tour-page";
import { WorkspacePage } from "./pages/workspace-page";

interface TourSearch {
  readonly projectId?: string;
  readonly draftId?: string;
  readonly contractId?: string;
  readonly runId?: string;
}

interface WorkspaceSearch {
  readonly projectId?: string;
  readonly draftId?: string;
  readonly contractId?: string;
  readonly runId?: string;
}

function optionalIdentifier(
  search: Record<string, unknown>,
  key: string,
): string | undefined {
  const value = search[key];
  if (value === undefined) return undefined;
  if (typeof value !== "string" || !value.trim() || value.length > 128) {
    throw new Error(`Invalid ${key} search parameter.`);
  }
  return value;
}

function validateTourSearch(search: Record<string, unknown>): TourSearch {
  return {
    projectId: optionalIdentifier(search, "projectId"),
    draftId: optionalIdentifier(search, "draftId"),
    contractId: optionalIdentifier(search, "contractId"),
    runId: optionalIdentifier(search, "runId"),
  };
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

function TourRoute() {
  const search = tourRoute.useSearch();
  return (
    <TourPage
      key={`${search.projectId ?? ""}:${search.draftId ?? ""}:${search.contractId ?? ""}:${search.runId ?? ""}`}
      {...search}
    />
  );
}

function WorkspaceRoute() {
  const search = workspaceRoute.useSearch();
  return (
    <WorkspacePage
      key={`${search.projectId ?? ""}:${search.draftId ?? ""}:${search.contractId ?? ""}:${search.runId ?? ""}`}
      {...search}
    />
  );
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

const rootRoute = createRootRouteWithContext<WorkspaceRuntimeBoundaries>()({
  component: RootLayout,
  errorComponent: RouteErrorPage,
  notFoundComponent: NotFoundPage,
});

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: EntryPage,
});

const tourRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/tour",
  validateSearch: validateTourSearch,
  component: TourRoute,
});

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workspace",
  validateSearch: validateWorkspaceSearch,
  component: WorkspaceRoute,
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
