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
  CreateResearchContractDraftInput,
  CreateResearchProjectInput,
  CreateResearchRunInput,
  RunDecisionInput,
  PaperAcquisitionRepository,
  PaperSummaryRepository,
  ScientificArtifactRepository,
  DataArtifactRepository,
  GraphArtifactRepository,
  LiteratureArtifactRepository,
  ProjectRepository,
  ResearchCatalogRepository,
  ResearchThreadRepository,
  ResearchThreadPage,
  RepositoryProvenance,
  RepositorySet,
  ResearchProjectPage,
  RunEventRecovery,
  RunRepository,
  ResearchInputRepository,
  SubmitResearchTurnInput,
  UpdateResearchProjectInput,
  ShareRepository,
  UpdateResearchContractDraftInput,
  WorkspaceSnapshotRepository,
} from "./ports";

export {
  createArtifactExportRepository,
  createFixtureArtifactExportRepository,
} from "./artifact-export-repository";
export {
  createDataArtifactRepository,
  createFixtureDataArtifactRepository,
} from "./data-artifact-repository";
export {
  createFixtureGraphArtifactRepository,
  createGraphArtifactRepository,
} from "./graph-artifact-repository";
export {
  createFixtureLiteratureArtifactRepository,
  createLiteratureArtifactRepository,
  mapLiteratureClaimRead,
  mapLiteratureRelationRead,
} from "./literature-artifact-repository";

export {
  createScientificArtifactRepository,
  mapScientificArtifactRead,
} from "./scientific-artifact-repository";

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
