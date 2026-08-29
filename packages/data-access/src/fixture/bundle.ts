/**
 * Fixture bundle type with explicit identity and provenance.
 *
 * A fixture bundle carries deterministic Demo Replay data for the Guided Tour
 * and workspace previews. Every bundle declares its scenario, schema version,
 * execution/source semantics and a human-readable provenance note so the UI
 * can unambiguously label the data as Demo Replay.
 */

import type {
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  ArtifactVersionDto,
  DatasetArtifactRead,
  FieldDictionaryArtifactRead,
  GraphArtifactRead,
  GraphEdgeRead,
  GraphNodeRead,
  LiteratureClaimRead,
  LiteratureRelationRead,
  PaperCollectionCandidateRead as PaperCollectionCandidateReadDto,
  PaperCollectionRead as PaperCollectionReadDto,
  PaperSummaryRead as PaperSummaryReadDto,
  PublicArtifactPresentation,
  ScientificArtifactRead as ScientificArtifactReadDto,
  SourceCollectionArtifactRead,
  ResearchArtifactDto,
  ResearchContractDto,
  ResearchContractDraftDto,
  ResearchProjectDto,
  ResearchRunDto,
  RunEventDto,
} from "@xingwen/contracts";
import type { Evidence, ResearchThreadEntry } from "@xingwen/domain";

type DataArtifactRead =
  | DatasetArtifactRead
  | FieldDictionaryArtifactRead
  | SourceCollectionArtifactRead;

/**
 * One PaperCollection API paper acquisition read model pinned to an ArtifactVersion id,
 * with its candidate reads in authoritative server ranking order.
 */
export interface FixturePaperAcquisition {
  /** Full immutable version as returned by the real Artifact detail boundary. */
  readonly version: ArtifactVersionDetailDto;
  readonly collection: PaperCollectionReadDto;
  readonly candidates: readonly PaperCollectionCandidateReadDto[];
}

/** One PaperSummary API paper summary read model pinned to an ArtifactVersion id. */
export interface FixturePaperSummary {
  /** Full immutable version as returned by the real Artifact detail boundary. */
  readonly version: ArtifactVersionDetailDto;
  readonly summary: PaperSummaryReadDto;
}

export interface FixtureBundleData {
  readonly projects: readonly ResearchProjectDto[];
  /** Public research conversation entries shown on the primary thread path. */
  readonly threadEntries: readonly ResearchThreadEntry[];
  readonly contractDrafts: readonly ResearchContractDraftDto[];
  readonly contracts: readonly ResearchContractDto[];
  readonly runs: readonly ResearchRunDto[];
  readonly runEvents: readonly RunEventDto[];
  readonly artifacts: readonly ResearchArtifactDto[];
  readonly artifactVersions: readonly ArtifactVersionDto[];
  /** Rich paper acquisition reads keyed by their artifact_version_id. */
  readonly paperAcquisitions: readonly FixturePaperAcquisition[];
  /** Rich paper summary reads keyed by their artifact_version_id. */
  readonly paperSummaries: readonly FixturePaperSummary[];
  /** Formal typed data Artifact reads shared by fixture and HTTP mappers. */
  readonly dataArtifactReads: readonly DataArtifactRead[];
  readonly fieldDictionaryArtifactReads: readonly FieldDictionaryArtifactRead[];
  readonly sourceCollectionArtifactReads: readonly SourceCollectionArtifactRead[];
  /** Formal typed Literature reads shared by fixture and HTTP mappers. */
  readonly literatureClaimReads: readonly LiteratureClaimRead[];
  readonly literatureRelationReads: readonly LiteratureRelationRead[];
  /** Formal typed Graph reads shared by fixture and HTTP mappers. */
  readonly graphArtifactReads: readonly GraphArtifactRead[];
  readonly graphNodeReads: readonly GraphNodeRead[];
  readonly graphEdgeReads: readonly GraphEdgeRead[];
  /** Formal typed Scientific reads shared by fixture and HTTP mappers. */
  readonly scientificArtifactReads?: readonly ScientificArtifactReadDto[];
  /** Frozen positive-contract presentations keyed by ArtifactVersion id. */
  readonly artifactPresentations: Readonly<
    Record<string, PublicArtifactPresentation>
  >;
  /**
   * Evidence is a frontend domain entity without a standalone transport
   * schema, so fixture evidence is provided directly in domain (camelCase)
   * form rather than as a validated DTO.
   */
  readonly evidence: readonly Evidence[];
}

export interface FixtureBundle {
  /** Human-readable scenario identifier, e.g. `exoplanet-host-star`. */
  readonly scenario: string;
  /** Contract schema version the fixture was authored against. */
  readonly schemaVersion: string;
  /** Always `demo_replay` for fixtures. */
  readonly executionMode: "demo_replay";
  /** Always `fixture` for fixture data. */
  readonly sourceMode: "fixture";
  /**
   * Provenance note displayed to users so Demo Replay data is never confused
   * with live or cached results.
   */
  readonly provenanceNote: string;
  /** Deterministic ISO 8601 timestamp marking when the fixture was generated. */
  readonly generatedAt: string;
  readonly data: FixtureBundleData;
}
