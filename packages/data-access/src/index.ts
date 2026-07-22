/**
 * @xingwen/data-access — repository ports and the Demo Replay fixture adapter.
 *
 * The public API exposes:
 * - Repository Port interfaces (operating on domain types, never DTOs).
 * - The versioned fixture bundle type and the frozen main-case fixture.
 * - `createFixtureRepositories` — validates DTOs against B-15 JSON Schemas,
 *   enforces Demo Replay semantics, and returns a ready-to-use `RepositorySet`.
 *
 * The HTTP adapter (A-15) will implement the same ports against `/api/v2`.
 */

export type {
  ArtifactRepository,
  ContractRepository,
  EvidenceRepository,
  Listener,
  ProjectRepository,
  RepositoryProvenance,
  RepositorySet,
  RunRepository,
  Unsubscribe,
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
  type FixtureRepositorySet,
} from "./fixture-adapter";
