/**
 * @xingwen/data-access — repository ports, the Demo Replay fixture adapter,
 * and the HTTP adapter for live `/api/v2` endpoints.
 *
 * The public API exposes:
 * - Narrowed Repository Port interfaces (operating on domain types, never DTOs).
 * - The versioned fixture bundle type and the frozen main-case fixture.
 * - `createFixtureRepositories` — validates DTOs against B-15 JSON Schemas,
 *   enforces Demo Replay semantics, and returns a ready-to-use `RepositorySet`.
 * - `createHttpRepositories` — implements the same ports against `/api/v2`,
 *   reusing the shared mapping layer so Fixture/HTTP consistency is
 *   guaranteed by construction.
 * - `createSessionManager` — anonymous session lifecycle and CSRF handling.
 * - HTTP error types mapping RFC 9457 Problem Details to domain errors.
 */

export type {
  ArtifactReadRepository,
  ContractRepository,
  CreateResearchRunInput,
  ProjectRepository,
  RepositoryProvenance,
  RepositorySet,
  RunEventRecovery,
  RunRepository,
  ShareRepository,
  UpdateResearchContractDraftInput,
  WorkspaceSnapshotRepository,
} from "./ports";

export {
  EntityNotFoundError,
  FixtureSemanticError,
  FixtureValidationError,
} from "./errors";

export type { FixtureBundle, FixtureBundleData } from "./fixture/bundle";
export { exoplanetHostStarFixture } from "./fixture/exoplanet-host-star";
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
export {
  createSessionManager,
  type SessionInfo,
  type SessionManager,
  type SessionManagerConfig,
  type SessionQuota,
} from "./session";
export {
  ConflictError,
  ForbiddenError,
  NetworkError,
  NotFoundError,
  RateLimitedError,
  SessionExpiredError,
  UnexpectedHttpError,
  UpstreamError,
  ValidationError,
  mapProblemDetails,
  type ProblemDetails,
  type ProblemDetailsFieldError,
} from "./http-errors";
