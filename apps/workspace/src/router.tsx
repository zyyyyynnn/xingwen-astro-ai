import {
  Link,
  Outlet,
  createRootRoute,
  createRoute,
  createRouter,
} from "@tanstack/react-router";
import type {
  ErrorComponentProps,
  RouterHistory,
} from "@tanstack/react-router";
import { ProductIdentity } from "@xingwen/ui";

function RootLayout() {
  return (
    <div className="workspace-shell">
      <a className="skip-link" href="#main-content">
        跳到主要内容
      </a>
      <header className="workspace-header">
        <ProductIdentity />
        <nav aria-label="主要导航">
          <Link to="/">入口</Link>
          <Link to="/tour">引导</Link>
          <Link to="/workspace">工作区</Link>
        </nav>
      </header>
      <main id="main-content" className="workspace-main">
        <Outlet />
      </main>
    </div>
  );
}

interface PageIdentityProps {
  eyebrow: string;
  title: string;
  description: string;
  detail?: string;
}

function PageIdentity({
  eyebrow,
  title,
  description,
  detail,
}: PageIdentityProps) {
  return (
    <section className="route-identity" aria-labelledby="route-title">
      <p className="eyebrow">{eyebrow}</p>
      <h1 id="route-title">{title}</h1>
      <p>{description}</p>
      {detail ? <p className="route-detail">{detail}</p> : null}
      <p className="baseline-note">
        当前仅提供 A-01 运行时、路由与可访问性基线，不包含科研业务行为。
      </p>
    </section>
  );
}

function EntryPage() {
  return (
    <PageIdentity
      eyebrow="Workspace entry"
      title="科研工作台入口"
      description="确认独立 React 应用、路由与共享包边界可运行。"
    />
  );
}

function TourPage() {
  return (
    <PageIdentity
      eyebrow="Guided tour"
      title="引导入口"
      description="保留引导路径身份；完整引导流程由后续事项实现。"
    />
  );
}

function WorkspacePage() {
  return (
    <PageIdentity
      eyebrow="Research workspace"
      title="科研工作区"
      description="保留工作区路径身份；Project、Run 与 Artifact 行为尚未接入。"
    />
  );
}

function SharePage() {
  return (
    <PageIdentity
      eyebrow="Shared result"
      title="共享入口"
      description="保留共享深链接身份；本轮不读取或展示共享数据。"
    />
  );
}

function LoadingPage() {
  return (
    <section className="route-identity" aria-busy="true" aria-live="polite">
      <p className="eyebrow">Loading</p>
      <h1>正在载入入口</h1>
    </section>
  );
}

function RouteErrorPage({ reset }: ErrorComponentProps) {
  return (
    <section className="route-identity" role="alert">
      <p className="eyebrow">Route error</p>
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
    <section className="route-identity">
      <p className="eyebrow">404</p>
      <h1>页面未找到</h1>
      <p>请求的工作台入口不存在。</p>
      <Link className="text-link" to="/">
        返回工作台入口
      </Link>
    </section>
  );
}

const rootRoute = createRootRoute({
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

export function createAppRouter(history?: RouterHistory) {
  return createRouter({
    routeTree,
    history,
    defaultErrorComponent: RouteErrorPage,
    defaultNotFoundComponent: NotFoundPage,
    defaultPendingComponent: LoadingPage,
    defaultPendingMinMs: 150,
    defaultPreload: "intent",
  });
}

export const router = createAppRouter();

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
