import type { DomainBoundary } from "@xingwen/domain";

/** Public workspace orchestration boundary only. Implementation starts with issue A-03. */
export interface WorkspaceCoreBoundary {
  readonly domain: DomainBoundary;
  readonly implementationStatus: "pending";
  readonly trackedIssue: "A-03";
}
