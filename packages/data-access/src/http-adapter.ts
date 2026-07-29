/**
 * HTTP adapter — composes the live `/api/v2` RepositorySet from focused
 * transport modules:
 *
 * - `http-client`            — fetch, envelopes, error mapping, CSRF, 401
 * - `research-repositories`  — Project / ContractDraft / Contract / Run / Event
 * - `artifact-repository`    — Artifact / ArtifactVersion / Evidence reads
 * - `snapshot-share-repositories` — WorkspaceSnapshot / Share
 *
 * Each read/write is validated against the generated contract and mapped into
 * the domain model via the shared `mapping.ts`; consistency tests compare that
 * path with the fixture adapter. The transport does not fabricate a source/exec
 * mode: provenance is read from the Run/ArtifactVersion domain objects.
 */

import { HttpClient } from "./http-client";
import type { HttpAdapterConfig } from "./http-client";
import { createArtifactRepository } from "./artifact-repository";
import { createPaperAcquisitionRepository } from "./paper-acquisition-repository";
import { createPaperSummaryRepository } from "./paper-summary-repository";
import type { RepositorySet } from "./ports";
import { createResearchRepositories } from "./research-repositories";
import { createSnapshotShareRepositories } from "./snapshot-share-repositories";

export type { HttpAdapterConfig };

/** The live `/api/v2` RepositorySet (identical port surface to the fixture). */
export type HttpRepositorySet = RepositorySet;

/**
 * Create a `RepositorySet` backed by real `/api/v2` endpoints.
 *
 * Reads issue GETs and map DTOs via the shared `mapping.ts`. Writes issue
 * POST/PATCH/PUT/DELETE with CSRF attached and the contract-required
 * `If-Match` / `Idempotency-Key` headers. 401 responses trigger the session
 * manager's expired notification.
 */
export function createHttpRepositories(
  config: HttpAdapterConfig,
): HttpRepositorySet {
  const http = new HttpClient(config);
  const { projects, contracts, runs } = createResearchRepositories(http);
  const artifacts = createArtifactRepository(http);
  const paperAcquisition = createPaperAcquisitionRepository(http);
  const paperSummary = createPaperSummaryRepository(http);
  const { workspaces, shares } = createSnapshotShareRepositories(http);
  return {
    projects,
    contracts,
    runs,
    artifacts,
    paperAcquisition,
    paperSummary,
    workspaces,
    shares,
  };
}
