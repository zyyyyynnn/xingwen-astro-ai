import type { ContractBoundary } from "@xingwen/contracts";
import type { DomainEntityId } from "@xingwen/domain";

/** Public Repository boundary only. Implementation starts with issue A-04. */
export interface DataAccessBoundary {
  readonly implementationStatus: "pending";
  readonly trackedIssue: "A-04";
}

export interface DataAccessTypeDependencies {
  readonly contract: ContractBoundary;
  readonly entityId: DomainEntityId;
}
