/**
 * HTTP adapter — composes the live `/api` RepositorySet from focused
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
import { createArtifactExportRepository } from "./artifact-export-repository";
import { createArtifactRepository } from "./artifact-repository";
import { createDataArtifactRepository } from "./data-artifact-repository";
import { createGraphArtifactRepository } from "./graph-artifact-repository";
import { createScientificArtifactRepository } from "./scientific-artifact-repository";
import { createLiteratureArtifactRepository } from "./literature-artifact-repository";
import { createPaperAcquisitionRepository } from "./paper-acquisition-repository";
import { createPaperSummaryRepository } from "./paper-summary-repository";
import type { RepositorySet } from "./ports";
import { createResearchRepositories } from "./research-repositories";
import { createResearchInputRepository } from "./research-input-repository";
import { createRevisionRepository } from "./revision-repository";
import { createSnapshotShareRepositories } from "./snapshot-share-repositories";
import { createModelProviderRepository } from "./model-provider-repository";

export type { HttpAdapterConfig };

/** The live `/api` RepositorySet (identical port surface to the fixture). */
export type HttpRepositorySet = RepositorySet;

/**
 * Create a `RepositorySet` backed by real `/api` endpoints.
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
  const { projects, researchCatalog, contracts, runs, researchThread } =
    createResearchRepositories(http);
  const artifacts = createArtifactRepository(http);
  const researchInputs = createResearchInputRepository(http);
  const paperAcquisition = createPaperAcquisitionRepository(http);
  const paperSummary = createPaperSummaryRepository(http);
  const dataArtifacts = createDataArtifactRepository(http);
  const literatureArtifacts = createLiteratureArtifactRepository(http);
  const graphArtifacts = createGraphArtifactRepository(http);
  const scientificArtifacts = createScientificArtifactRepository(http);
  const artifactExports = createArtifactExportRepository(http);
  const revisions = createRevisionRepository(http);
  const { workspaces, shares } = createSnapshotShareRepositories(http);
  const modelProvider = createModelProviderRepository(http);
  return {
    projects,
    researchCatalog,
    researchThread,
    contracts,
    runs,
    artifacts,
    researchInputs,
    paperAcquisition,
    paperSummary,
    dataArtifacts,
    literatureArtifacts,
    graphArtifacts,
    scientificArtifacts,
    artifactExports,
    revisions,
    workspaces,
    shares,
    modelProvider,
  };
}
