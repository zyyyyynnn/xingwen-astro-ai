/**
 * UI navigation preferences: pinned projects, recent project access and the
 * last viewed project. Pure UI state; never mixed into server-owned truth.
 */

const PINNED_PROJECTS_KEY = "xingwen.pinned-projects";
const PROJECT_ACCESS_KEY = "xingwen.project-access";

export type ProjectAccessLog = Record<string, string>;

export function readPinnedProjects(): readonly string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(
      window.localStorage.getItem(PINNED_PROJECTS_KEY) ?? "[]",
    );
    return Array.isArray(value)
      ? value.filter((item): item is string => typeof item === "string")
      : [];
  } catch {
    return [];
  }
}

export function writePinnedProjects(projectIds: readonly string[]): void {
  window.localStorage.setItem(PINNED_PROJECTS_KEY, JSON.stringify(projectIds));
}

export function readProjectAccess(): ProjectAccessLog {
  if (typeof window === "undefined") return {};
  try {
    const value = JSON.parse(
      window.localStorage.getItem(PROJECT_ACCESS_KEY) ?? "{}",
    );
    return value !== null && typeof value === "object"
      ? (value as ProjectAccessLog)
      : {};
  } catch {
    return {};
  }
}

export function writeProjectAccess(log: ProjectAccessLog): void {
  window.localStorage.setItem(PROJECT_ACCESS_KEY, JSON.stringify(log));
}

/** Most recently accessed project id, or null when nothing was opened yet. */
export function lastViewedProjectId(
  log: ProjectAccessLog = readProjectAccess(),
): string | null {
  return (
    Object.entries(log).sort(([, left], [, right]) =>
      right.localeCompare(left),
    )[0]?.[0] ?? null
  );
}
