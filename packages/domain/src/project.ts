/**
 * Research project — the top-level aggregate for a research investigation.
 *
 * Mirrors `ResearchProject` in the Pydantic `/api` authoring source.
 */

import type { CaseKey } from "./value-types";
import type { DomainEntityId } from "./identifiers";
import type { UtcIsoTimestamp } from "./value-types";

export interface ResearchProject {
  readonly id: DomainEntityId;
  readonly sessionId: DomainEntityId;
  readonly name: string;
  readonly description: string;
  readonly caseKey: CaseKey;
  readonly activeContractId: DomainEntityId | null;
  readonly latestRunId: DomainEntityId | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly updatedAt: UtcIsoTimestamp;
  readonly revision: number;
}
