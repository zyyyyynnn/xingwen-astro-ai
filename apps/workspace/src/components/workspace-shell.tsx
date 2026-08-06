import type { ReactNode } from "react";
import { BrandMark } from "@xingwen/ui";

export interface WorkspaceShellProps {
  readonly navigator: ReactNode;
  readonly missionHeader: ReactNode;
  readonly missionSpine?: ReactNode;
  readonly contextRail: ReactNode;
  readonly composer?: ReactNode;
  readonly children: ReactNode;
  readonly headerBrand?: ReactNode;
  readonly headerBreadcrumb?: ReactNode;
  readonly headerActions?: ReactNode;
}

/** Presentation-only three-section layout for the A-17 research workbench. */
export function WorkspaceShell({
  navigator,
  missionHeader,
  missionSpine,
  contextRail,
  composer,
  children,
  headerBrand,
  headerBreadcrumb,
  headerActions,
}: WorkspaceShellProps) {
  return (
    <div className="workspace-shell-a17">
      <a className="skip-link" href="#main-stage-content">
        跳到主舞台
      </a>
      <header className="workspace-shell-a17__header" role="banner">
        <div className="workspace-shell-a17__header-brand">
          {headerBrand ?? <BrandMark />}
        </div>
        {headerBreadcrumb ? (
          <div className="workspace-shell-a17__header-breadcrumb">
            {headerBreadcrumb}
          </div>
        ) : null}
        {headerActions ? (
          <div className="workspace-shell-a17__header-actions">
            {headerActions}
          </div>
        ) : null}
      </header>
      <div className="workspace-shell-a17__body">
        <aside
          className="workspace-shell-a17__navigator"
          aria-label="Research Navigator"
        >
          {navigator}
        </aside>
        <main
          id="main-stage"
          className="workspace-shell-a17__main"
          role="main"
          tabIndex={-1}
        >
          {missionHeader ? (
            <div className="workspace-shell-a17__mission-header">
              {missionHeader}
            </div>
          ) : null}
          {missionSpine ? (
            <div className="workspace-shell-a17__mission-spine">
              {missionSpine}
            </div>
          ) : null}
          <div id="main-stage-content" className="workspace-shell-a17__content">
            {children}
          </div>
          {composer ? (
            <div className="workspace-shell-a17__composer">{composer}</div>
          ) : null}
        </main>
        <aside
          className="workspace-shell-a17__context-rail"
          aria-label="Research Context Rail"
        >
          {contextRail}
        </aside>
      </div>
    </div>
  );
}
