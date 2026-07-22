import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { BrandMark } from "@xingwen/ui";

export interface ResearchShellNavigation {
  readonly projectId?: string;
  readonly draftId?: string;
  readonly contractId?: string;
  readonly runId?: string;
}

export interface ResearchShellProps {
  readonly status: ReactNode;
  readonly atlas: ReactNode;
  readonly observatory: ReactNode;
  readonly console: ReactNode;
  readonly children: ReactNode;
  readonly navigation?: ResearchShellNavigation;
}

/** Presentation-only five-region layout for private research routes. */
export function ResearchShell({
  status,
  atlas,
  observatory,
  console,
  children,
  navigation,
}: ResearchShellProps) {
  const contextualSearch = {
    ...(navigation?.projectId ? { projectId: navigation.projectId } : {}),
    ...(navigation?.draftId ? { draftId: navigation.draftId } : {}),
    ...(navigation?.contractId ? { contractId: navigation.contractId } : {}),
    ...(navigation?.runId ? { runId: navigation.runId } : {}),
  };
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
          <Link to="/tour" search={contextualSearch}>
            引导
          </Link>
          <Link to="/workspace" search={contextualSearch}>
            工作区
          </Link>
        </nav>
        <span className="rail-status" aria-label="当前状态">
          {status}
        </span>
      </header>
      <div className="workspace-body">
        <aside className="research-atlas" aria-label="Research Atlas">
          <details className="region-details" open>
            <summary>Research Atlas</summary>
            {atlas}
          </details>
        </aside>
        <main
          id="research-canvas"
          className="research-canvas"
          role="main"
          tabIndex={-1}
        >
          {children}
        </main>
        <aside
          className="provenance-observatory"
          aria-label="Provenance Observatory"
        >
          <details className="region-details" open>
            <summary>Provenance Observatory</summary>
            {observatory}
          </details>
        </aside>
      </div>
      <footer className="research-console" aria-label="Research Console">
        {console}
      </footer>
    </div>
  );
}
