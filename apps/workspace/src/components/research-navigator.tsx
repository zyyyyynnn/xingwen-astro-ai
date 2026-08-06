import { useState } from "react";

export type ProjectUserStatus =
  "draft" | "running" | "needs_review" | "completed" | "failed";

export interface NavigatorProject {
  readonly id: string;
  readonly name: string;
  readonly userStatus: ProjectUserStatus;
  readonly currentPhase?: string;
  readonly pendingReviewCount?: number;
  readonly updatedAt: string;
  readonly latestRunId?: string | null;
}

export interface ResearchNavigatorProps {
  readonly projects: readonly NavigatorProject[];
  readonly activeProjectId: string | null;
  readonly pinnedProjectIds: readonly string[];
  readonly recentProjectIds: readonly string[];
  readonly onSelectProject: (project: NavigatorProject) => void;
  readonly onCreateProject: () => void;
  readonly onTogglePin?: (projectId: string) => void;
  readonly disabled?: boolean;
}

interface StatusGroupConfig {
  readonly status: ProjectUserStatus;
  readonly label: string;
  readonly className: string;
}

const STATUS_GROUPS: readonly StatusGroupConfig[] = [
  {
    status: "running",
    label: "进行中",
    className: "research-navigator__group--running",
  },
  {
    status: "needs_review",
    label: "待复核",
    className: "research-navigator__group--review",
  },
  {
    status: "completed",
    label: "已完成",
    className: "research-navigator__group--completed",
  },
  {
    status: "failed",
    label: "失败",
    className: "research-navigator__group--failed",
  },
  {
    status: "draft",
    label: "草稿",
    className: "research-navigator__group--draft",
  },
];

const STATUS_LABELS: Record<ProjectUserStatus, string> = {
  draft: "草稿",
  running: "进行中",
  needs_review: "待复核",
  completed: "已完成",
  failed: "失败",
};

function formatRelativeTime(iso: string): string {
  const date = new Date(iso);
  const diff = Date.now() - date.getTime();
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  return `${days} 天前`;
}

function ProjectItem({
  project,
  isActive,
  disabled,
  onSelect,
  onTogglePin,
}: {
  readonly project: NavigatorProject;
  readonly isActive: boolean;
  readonly disabled: boolean;
  readonly onSelect: () => void;
  readonly onTogglePin?: () => void;
}) {
  return (
    <li className="research-navigator__item-wrapper">
      <button
        type="button"
        className={`research-navigator__item ${isActive ? "research-navigator__item--active" : ""}`}
        onClick={onSelect}
        disabled={disabled}
        aria-current={isActive ? "true" : undefined}
      >
        <span className="research-navigator__item-title">{project.name}</span>
        <span className="research-navigator__item-meta">
          <span
            className="research-navigator__item-status"
            data-status={project.userStatus}
          >
            {STATUS_LABELS[project.userStatus]}
          </span>
          {project.currentPhase ? (
            <span className="research-navigator__item-phase">
              {project.currentPhase}
            </span>
          ) : null}
          {project.pendingReviewCount && project.pendingReviewCount > 0 ? (
            <span className="research-navigator__item-review">
              {project.pendingReviewCount} 待复核
            </span>
          ) : null}
          <span className="research-navigator__item-time">
            {formatRelativeTime(project.updatedAt)}
          </span>
        </span>
      </button>
      {onTogglePin ? (
        <button
          type="button"
          className="research-navigator__pin-toggle"
          onClick={onTogglePin}
          disabled={disabled}
          aria-label={isActive ? "取消固定" : "固定项目"}
        >
          {isActive ? "★" : "☆"}
        </button>
      ) : null}
    </li>
  );
}

function CollapsibleGroup({
  label,
  className,
  children,
}: {
  readonly label: string;
  readonly className?: string;
  readonly children: React.ReactNode;
}) {
  const [open, setOpen] = useState(true);
  return (
    <section className={`research-navigator__group ${className ?? ""}`}>
      <button
        type="button"
        className="research-navigator__group-toggle"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className="research-navigator__group-arrow" data-open={open}>
          ▸
        </span>
        <span className="research-navigator__group-title">{label}</span>
      </button>
      {open && <ul className="research-navigator__list">{children}</ul>}
    </section>
  );
}

/** Left sidebar: research projects grouped by status with Pin/Recent. */
export function ResearchNavigator({
  projects,
  activeProjectId,
  pinnedProjectIds,
  recentProjectIds,
  onSelectProject,
  onCreateProject,
  onTogglePin,
  disabled = false,
}: ResearchNavigatorProps) {
  const pinnedSet = new Set(pinnedProjectIds);
  const recentSet = new Set(recentProjectIds);
  const pinnedProjects = projects.filter((p) => pinnedSet.has(p.id));
  const recentProjects = projects.filter(
    (p) => recentSet.has(p.id) && !pinnedSet.has(p.id),
  );
  const remainingProjects = projects.filter(
    (p) => !pinnedSet.has(p.id) && !recentSet.has(p.id),
  );

  const byStatus = (status: ProjectUserStatus) =>
    remainingProjects.filter((p) => p.userStatus === status);

  const renderProject = (project: NavigatorProject) => (
    <ProjectItem
      key={project.id}
      project={project}
      isActive={project.id === activeProjectId}
      disabled={disabled}
      onSelect={() => onSelectProject(project)}
      onTogglePin={onTogglePin ? () => onTogglePin(project.id) : undefined}
    />
  );

  const hasContent =
    projects.length > 0 ||
    pinnedProjects.length > 0 ||
    recentProjects.length > 0;

  return (
    <nav className="research-navigator" aria-label="研究导航">
      <button
        type="button"
        className="research-navigator__create"
        onClick={onCreateProject}
        disabled={disabled}
      >
        新建研究
      </button>
      {!hasContent ? (
        <p className="region-placeholder">尚无研究项目。</p>
      ) : (
        <div className="research-navigator__groups">
          {pinnedProjects.length > 0 && (
            <CollapsibleGroup label="固定项目">
              {pinnedProjects.map(renderProject)}
            </CollapsibleGroup>
          )}
          {recentProjects.length > 0 && (
            <CollapsibleGroup label="最近访问">
              {recentProjects.map(renderProject)}
            </CollapsibleGroup>
          )}
          {STATUS_GROUPS.map((group) => {
            const items = byStatus(group.status);
            if (items.length === 0) return null;
            return (
              <CollapsibleGroup
                key={group.status}
                label={group.label}
                className={group.className}
              >
                {items.map(renderProject)}
              </CollapsibleGroup>
            );
          })}
        </div>
      )}
    </nav>
  );
}
