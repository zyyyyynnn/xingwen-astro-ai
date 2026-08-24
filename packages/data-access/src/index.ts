/**
 * @xingwen/data-access — repository ports, the Demo Replay fixture adapter,
 * and the HTTP adapter for live `/api` endpoints.
 *
 * The public API exposes:
 * - Narrowed Repository Port interfaces (operating on domain types, never DTOs).
 * - The versioned fixture bundle type and the frozen main-case fixture.
 * - `createFixtureRepositories` — validates DTOs against Core Domain and Transport Contract JSON Schemas,
 *   enforces Demo Replay semantics, and returns a ready-to-use `RepositorySet`.
 * - `createHttpRepositories` — implements the same ports against `/api`,
 *   reusing the shared mapping layer so Fixture/HTTP consistency is
 *   guaranteed by construction.
 * - `createSessionManager` — anonymous session lifecycle and CSRF handling.
 * - HTTP error types mapping RFC 9457 Problem Details to domain errors.
 */

export type {
  ArtifactExportRepository,
  ArtifactReadRepository,
  ContractRepository,
  CreateResearchInputInput,
  CreateResearchContractDraftInput,
  CreateResearchProjectInput,
  CreateResearchRunInput,
  CreateRevisionInput,
  DataArtifactRepository,
  GraphArtifactRepository,
  LiteratureArtifactRepository,
  ModelProviderRepository,
  PaperAcquisitionRepository,
  PaperSummaryRepository,
  ProjectRepository,
  ResearchCatalogRepository,
  ResearchInputRepository,
  RevisionRepository,
  ResearchInputRef,
  ResearchInputStatus,
  ResearchInputType,
  ResearchThreadRepository,
  ResearchThreadPage,
  RepositoryProvenance,
  RepositorySet,
  ResearchProjectPage,
  RunEventRecovery,
  RunRepository,
  SubmitResearchTurnInput,
  UpdateResearchProjectInput,
  ShareRepository,
  UpdateResearchContractDraftInput,
  WorkspaceSnapshotRepository,
} from "./ports";

export {
  ConflictError,
  EntityNotFoundError,
  ForbiddenError,
  FixtureSemanticError,
  FixtureValidationError,
  NetworkError,
  NotFoundError,
  RateLimitedError,
  SessionExpiredError,
  UnexpectedHttpError,
  UpstreamError,
  ValidationError,
} from "./errors";

export type {
  FixtureBundle,
  FixtureBundleData,
  FixturePaperAcquisition,
  FixturePaperSummary,
} from "./fixture/bundle";
export { exoplanetHostStarFixture } from "./fixture/exoplanet-host-star";
export {
  paperAcquisitionFixtureProvenance,
  paperCandidateReadsFixture,
  paperCollectionReadFixture,
} from "./fixture/paper-acquisition";
export {
  paperSummaryFixtureProvenance,
  paperSummaryReadFixture,
} from "./fixture/paper-summary";
export {
  assemblePaperSummaryReview,
  createPaperSummaryRepository,
} from "./paper-summary-repository";
export {
  createArtifactExportRepository,
  createFixtureArtifactExportRepository,
} from "./artifact-export-repository";
export {
  createDataArtifactRepository,
  createFixtureDataArtifactRepository,
} from "./data-artifact-repository";
export {
  createGraphArtifactRepository,
  createFixtureGraphArtifactRepository,
} from "./graph-artifact-repository";
export {
  createLiteratureArtifactRepository,
  createFixtureLiteratureArtifactRepository,
} from "./literature-artifact-repository";
export {
  createFixtureRepositories,
  type FixtureAdapterOptions,
  type FixtureRepositorySet,
} from "./fixture-adapter";

export {
  createHttpRepositories,
  type HttpAdapterConfig,
  type HttpRepositorySet,
} from "./http-adapter";
export { createResearchInputRepository } from "./research-input-repository";
export { createModelProviderRepository } from "./model-provider-repository";
export {
  createSessionManager,
  type SessionInfo,
  type SessionManager,
  type SessionManagerConfig,
  type SessionQuota,
} from "./session";
export {
  mapProblemDetails,
  type ProblemDetails,
  type ProblemDetailsFieldError,
} from "./http-errors";

export {
  createRevisionRepository,
  createFixtureRevisionRepository,
} from "./revision-repository";
