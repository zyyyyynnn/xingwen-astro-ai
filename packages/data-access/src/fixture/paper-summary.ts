/**
 * A-06 paper summary fixture — generated consumption layer.
 *
 * The actual data lives in `paper-summary.fixture.json`, which is built by
 * the real D-03 pipeline (`services/paper_pipeline/demo_summary_fixture.py`)
 * over the deterministic A-05 demo PaperCollection and validated by the
 * authoritative Pydantic contract gates in CI. Nothing scientific is authored
 * in TypeScript here.
 *
 * The JSON import is wider than the generated DTO types, so a single narrow
 * cast bridges the two; runtime validity is enforced by AJV in the fixture
 * adapter and by the Pydantic gate in CI, not by this cast.
 */

import type {
  ArtifactVersionDetail as ArtifactVersionDetailDto,
  PaperSummaryRead as PaperSummaryReadDto,
} from "@xingwen/contracts";

import fixtureDocument from "./paper-summary.fixture.json";

/** Generation provenance: tool, command, benchmark identity and demo note. */
export const paperSummaryFixtureProvenance = fixtureDocument.$generated;

/** The complete B-07 summary read pinned to `artv_papsum_01`. */
export const paperSummaryReadFixture =
  fixtureDocument.read as unknown as PaperSummaryReadDto;

/**
 * Full immutable ArtifactVersion projection derived from the same canonical
 * PaperSummary dump. The fixture adapter consumes its metadata exactly as
 * the HTTP Artifact detail repository does; rich content remains on the
 * dedicated paper-summary entry instead of being squeezed into the thin
 * generic ArtifactVersion DTO.
 */
export const paperSummaryArtifactVersionFixture =
  fixtureDocument.artifact_version as unknown as ArtifactVersionDetailDto;
