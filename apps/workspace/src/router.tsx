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
import { BrandMark } from "@xingwen/ui";
import type { WorkspaceRuntimeBoundaries } from "./boundaries";

function RootLayout() {
  return (
    <div className="workspace-shell">
      <a className="skip-link" href="#research-canvas">
        跳到研究画布
      </a>
      <header className="top-status-rail" role="banner">
        <BrandMark />
        <nav aria-label="主要导航">
          <Link to="/" activeOptions={{ exact: true }}>
            入口
          </Link>
          <Link to="/tour">引导</Link>
          <Link to="/workspace">工作区</Link>
        </nav>
        <span className="rail-status" aria-label="当前状态">
          占位状态
        </span>
      </header>
      <div className="workspace-body">
        <aside className="research-atlas" aria-label="Research Atlas">
          <p className="region-label">Research Atlas</p>
          <p className="region-placeholder">项目列表占位</p>
        </aside>
        <main
          id="research-canvas"
          className="research-canvas"
          role="main"
          tabIndex={-1}
        >
          <Outlet />
        </main>
        <aside
          className="provenance-observatory"
          aria-label="Provenance Observatory"
        >
          <p className="region-label">Provenance Observatory</p>
          <p className="region-placeholder">证据来源占位</p>
        </aside>
      </div>
      <footer className="research-console" aria-label="Research Console">
        <p className="region-label">Research Console</p>
        <p className="region-placeholder">研究指令台占位（收起）</p>
      </footer>
    </div>
  );
}

function EntryPage() {
  return (
    <section className="route-content" aria-labelledby="route-title">
      <h1 id="route-title">科研工作台入口</h1>
      <p>
        确认独立 React
        应用、路由与共享包边界可运行。完整科研业务行为由后续事项实现。
      </p>
    </section>
  );
}

function TourPage() {
  return (
    <section className="route-content" aria-labelledby="route-title">
      <h1 id="route-title">引导入口</h1>
      <p>保留引导路径身份；完整引导流程由后续事项实现。</p>
    </section>
  );
}

function WorkspacePage() {
  return (
    <section className="route-content" aria-labelledby="route-title">
      <h1 id="route-title">科研工作区</h1>
      <p>
        工作台 Shell 五区域已就位：Top Status Rail、Research Atlas、Research
        Canvas、Provenance Observatory 与 Research Console。Project、Run 与
        Artifact 行为尚未接入。
      </p>
    </section>
  );
}

function SharePage() {
  return (
    <section className="route-content" aria-labelledby="route-title">
      <h1 id="route-title">共享入口</h1>
      <p>保留共享深链接身份；本轮不读取或展示共享数据。</p>
    </section>
  );
}

function LoadingPage() {
  return (
    <section className="route-content" aria-busy="true" aria-live="polite">
      <h1>正在载入入口</h1>
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
  component: TourPage,
});

const workspaceRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/workspace",
  component: WorkspacePage,
});

const shareRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/share/$shareToken",
  component: SharePage,
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
