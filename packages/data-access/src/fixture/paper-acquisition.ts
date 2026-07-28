/**
 * A-05 paper acquisition fixture — generated consumption layer.
 *
 * The actual data lives in `paper-acquisition.fixture.json`, which is built by
 * the real D-02 pipeline (`services/paper_pipeline/demo_fixture.py`) against
 * the frozen benchmark and validated by the authoritative Pydantic contract in
 * `apps/api/tests/test_paper_acquisition_fixture.py` (positive + negative
 * gates, drift check against a deterministic rebuild). Nothing scientific is
 * authored in TypeScript here.
 *
 * The JSON import is wider than the generated DTO types, so a single narrow
 * cast bridges the two; runtime validity is enforced by AJV in the fixture
 * adapter and by the Pydantic gate in CI, not by this cast.
 */

import type {
  PaperCollectionCandidateRead as PaperCollectionCandidateReadDto,
  PaperCollectionRead as PaperCollectionReadDto,
} from "@xingwen/contracts";

import fixtureDocument from "./paper-acquisition.fixture.json";

/** Generation provenance: tool, command, benchmark identity and demo note. */
export const paperAcquisitionFixtureProvenance = fixtureDocument.$generated;

/** The complete B-06 collection read pinned to `artv_papcol_01`. */
export const paperCollectionReadFixture =
  fixtureDocument.read as unknown as PaperCollectionReadDto;

/** Candidate reads in the authoritative server ranking order. */
export const paperCandidateReadsFixture =
  fixtureDocument.candidate_reads as unknown as readonly PaperCollectionCandidateReadDto[];
