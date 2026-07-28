/**
 * Paper acquisition fixture — the frozen main-case Demo Replay data for the
 * A-05 candidate review workspace (B-06 read contract).
 *
 * Deterministic, contract-valid `PaperCollectionRead` +
 * `PaperCollectionCandidateRead` payloads pinned to the existing
 * `artv_papcol_01` version (same content/input hashes as the ArtifactVersion
 * entry). The scenario intentionally covers: selected and excluded
 * candidates, a duplicate group with an uncertain-match conflict, two
 * sources, per-candidate SourceSnapshot + Evidence, benchmark metadata and a
 * non-http candidate URL (must render as plain text, never a link).
 *
 * This is hand-authored demonstration data: `source_mode` is always
 * `fixture` and it must never be presented as a live retrieval.
 */

import type {
  EvidenceDetail as EvidenceDetailDto,
  PaperCollectionCandidate as PaperCollectionCandidateDto,
  PaperCollectionCandidateRead as PaperCollectionCandidateReadDto,
  PaperCollectionRead as PaperCollectionReadDto,
  PaperDuplicateGroup as PaperDuplicateGroupDto,
  SourceSnapshotDetail as SourceSnapshotDetailDto,
} from "@xingwen/contracts";

const T_STARTED = "2026-07-21T08:24:00Z";
const T_RETRIEVED = "2026-07-21T08:24:30Z";
const T_FINISHED = "2026-07-21T08:25:00Z";

function hash(char: string): string {
  return `sha256:${char.repeat(64)}`;
}

const pagination = {
  candidate_limit: 100,
  max_pages: 2,
  page_size: 50,
} as const;

const adsSnapshot: SourceSnapshotDetailDto = {
  id: "snap_paper_ads_01",
  source_id: "nasa_ads",
  source_type: "paper_index",
  retrieved_at: T_RETRIEVED,
  query:
    "toi-1234 host star parameters" as unknown as SourceSnapshotDetailDto["query"],
  query_hash: hash("d"),
  source_version_or_etag: null,
  content_hash: hash("4"),
  license_note: "NASA ADS metadata terms; fixture data, not a live query",
  cache_version: null,
  request_metadata: {},
};

const arxivSnapshot: SourceSnapshotDetailDto = {
  id: "snap_paper_arxiv_01",
  source_id: "arxiv",
  source_type: "paper_index",
  retrieved_at: T_RETRIEVED,
  query:
    "toi-1234 host star parameters" as unknown as SourceSnapshotDetailDto["query"],
  query_hash: hash("d"),
  source_version_or_etag: null,
  content_hash: hash("5"),
  license_note: "arXiv metadata terms; fixture data, not a live query",
  cache_version: null,
  request_metadata: {},
};

function paperEvidence(
  id: string,
  targetId: string,
  snapshot: SourceSnapshotDetailDto,
  recordId: string,
  quote: string,
): EvidenceDetailDto {
  return {
    id,
    artifact_version_id: "artv_papcol_01",
    target_type: "paper",
    target_id: targetId,
    evidence_type: "paper_search",
    source_snapshot_id: snapshot.id,
    paper_id: null,
    locator: {
      kind: "database_cell",
      query_hash: snapshot.query_hash,
      row_key: recordId,
      field: "paper.title",
    } as unknown as EvidenceDetailDto["locator"],
    quote_or_value: quote as unknown as EvidenceDetailDto["quote_or_value"],
    extraction_method: "paper_acquisition.source_record",
    confidence: 1,
    created_at: T_FINISHED,
  };
}

const evidence: readonly EvidenceDetailDto[] = [
  paperEvidence(
    "evd_paper_01",
    "cand_paper_01",
    adsSnapshot,
    "ads_2025_toi1234b",
    "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
  ),
  paperEvidence(
    "evd_paper_02",
    "cand_paper_02",
    arxivSnapshot,
    "arxiv_2405_01234",
    "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
  ),
  paperEvidence(
    "evd_paper_03",
    "cand_paper_03",
    arxivSnapshot,
    "arxiv_2406_05678",
    "Host-star Parameters of TOI-1234 from High-resolution Spectroscopy",
  ),
  paperEvidence(
    "evd_paper_04",
    "cand_paper_04",
    adsSnapshot,
    "ads_2023_flares",
    "A Survey of Unrelated M-dwarf Flares",
  ),
];

const duplicateGroups: readonly PaperDuplicateGroupDto[] = [
  {
    duplicate_group_id: "dupg_01",
    canonical_paper_id: "paper_01",
    candidate_ids: ["cand_paper_01", "cand_paper_02"],
    match_basis: ["doi"],
    conflicts: [
      {
        classification: "uncertain_match",
        field: "year",
        detail: "ADS reports 2025 while the arXiv preprint reports 2024",
        related_candidate_id: "cand_paper_02",
      },
    ],
  },
  {
    duplicate_group_id: "dupg_02",
    canonical_paper_id: "paper_02",
    candidate_ids: ["cand_paper_03"],
    match_basis: ["arxiv_id"],
    conflicts: [],
  },
  {
    duplicate_group_id: "dupg_03",
    canonical_paper_id: "paper_03",
    candidate_ids: ["cand_paper_04"],
    match_basis: ["source_record"],
    conflicts: [],
  },
];

const candidates: readonly PaperCollectionCandidateDto[] = [
  {
    candidate_id: "cand_paper_01",
    canonical_paper_id: "paper_01",
    canonical_identity_basis: "doi",
    duplicate_group_id: "dupg_01",
    title: "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
    normalized_title: "toi-1234 b validation of a hot jupiter around tic-5678",
    authors: ["A. Astronomer", "B. Researcher"],
    normalized_authors: ["a astronomer", "b researcher"],
    year: 2025,
    doi: "10.1234/toi-1234b",
    arxiv_id: null,
    url: "https://ui.adsabs.harvard.edu/abs/2025toi1234b",
    ranking_key: "0001",
    ranking_rule_version: "1.0.0",
    relevance_score: 0.97,
    selected: true,
    selection_reason:
      "Top-ranked validated planet paper covering the contracted fields",
    selection_rule_version: "1.0.0",
    exclusion_reason: null,
    conflicts: [
      {
        classification: "uncertain_match",
        field: "year",
        detail: "ADS reports 2025 while the arXiv preprint reports 2024",
        related_candidate_id: "cand_paper_02",
      },
    ],
    dedupe_evidence: [],
    raw: {
      source_id: "nasa_ads",
      source_record_id: "ads_2025_toi1234b",
      source_snapshot_id: "snap_paper_ads_01",
      record_hash: hash("6"),
      title: "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
      authors: ["A. Astronomer", "B. Researcher"],
      year: 2025,
      doi: "10.1234/toi-1234b",
      arxiv_id: null,
      url: "https://ui.adsabs.harvard.edu/abs/2025toi1234b",
    },
  },
  {
    candidate_id: "cand_paper_02",
    canonical_paper_id: "paper_01",
    canonical_identity_basis: "doi",
    duplicate_group_id: "dupg_01",
    title: "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
    normalized_title: "toi-1234 b validation of a hot jupiter around tic-5678",
    authors: ["A. Astronomer", "B. Researcher"],
    normalized_authors: ["a astronomer", "b researcher"],
    year: 2024,
    doi: "10.1234/toi-1234b",
    arxiv_id: "2405.01234",
    url: "https://arxiv.org/abs/2405.01234",
    ranking_key: "0002",
    ranking_rule_version: "1.0.0",
    relevance_score: 0.95,
    selected: false,
    selection_reason: null,
    selection_rule_version: "1.0.0",
    exclusion_reason: "Duplicate of canonical paper paper_01 (DOI match)",
    conflicts: [
      {
        classification: "uncertain_match",
        field: "year",
        detail: "ADS reports 2025 while the arXiv preprint reports 2024",
        related_candidate_id: "cand_paper_01",
      },
    ],
    dedupe_evidence: ["evd_paper_02"],
    raw: {
      source_id: "arxiv",
      source_record_id: "arxiv_2405_01234",
      source_snapshot_id: "snap_paper_arxiv_01",
      record_hash: hash("7"),
      title: "TOI-1234 b: Validation of a Hot Jupiter Around TIC-5678",
      authors: ["A. Astronomer", "B. Researcher"],
      year: 2024,
      doi: "10.1234/toi-1234b",
      arxiv_id: "2405.01234",
      url: "https://arxiv.org/abs/2405.01234",
    },
  },
  {
    candidate_id: "cand_paper_03",
    canonical_paper_id: "paper_02",
    canonical_identity_basis: "arxiv_id",
    duplicate_group_id: "dupg_02",
    title: "Host-star Parameters of TOI-1234 from High-resolution Spectroscopy",
    normalized_title:
      "host-star parameters of toi-1234 from high-resolution spectroscopy",
    authors: ["C. Spectroscopist"],
    normalized_authors: ["c spectroscopist"],
    year: 2024,
    doi: null,
    arxiv_id: "2406.05678",
    url: "https://arxiv.org/abs/2406.05678",
    ranking_key: "0003",
    ranking_rule_version: "1.0.0",
    relevance_score: 0.88,
    selected: true,
    selection_reason: "Covers the contracted host-star parameter fields",
    selection_rule_version: "1.0.0",
    exclusion_reason: null,
    conflicts: [],
    dedupe_evidence: [],
    raw: {
      source_id: "arxiv",
      source_record_id: "arxiv_2406_05678",
      source_snapshot_id: "snap_paper_arxiv_01",
      record_hash: hash("8"),
      title:
        "Host-star Parameters of TOI-1234 from High-resolution Spectroscopy",
      authors: ["C. Spectroscopist"],
      year: 2024,
      doi: null,
      arxiv_id: "2406.05678",
      url: "https://arxiv.org/abs/2406.05678",
    },
  },
  {
    candidate_id: "cand_paper_04",
    canonical_paper_id: "paper_03",
    canonical_identity_basis: "source_record",
    duplicate_group_id: "dupg_03",
    title: "A Survey of Unrelated M-dwarf Flares",
    normalized_title: "a survey of unrelated m-dwarf flares",
    authors: ["D. Surveyor"],
    normalized_authors: ["d surveyor"],
    year: 2023,
    doi: null,
    arxiv_id: null,
    url: "ftp://mirror.example.org/flares.pdf",
    ranking_key: "0004",
    ranking_rule_version: "1.0.0",
    relevance_score: 0.31,
    selected: false,
    selection_reason: null,
    selection_rule_version: "1.0.0",
    exclusion_reason: "Relevance 0.31 is below the selection threshold",
    conflicts: [],
    dedupe_evidence: [],
    raw: {
      source_id: "nasa_ads",
      source_record_id: "ads_2023_flares",
      source_snapshot_id: "snap_paper_ads_01",
      record_hash: hash("9"),
      title: "A Survey of Unrelated M-dwarf Flares",
      authors: ["D. Surveyor"],
      year: 2023,
      doi: null,
      arxiv_id: null,
      url: "ftp://mirror.example.org/flares.pdf",
    },
  },
];

/** The complete collection read model pinned to `artv_papcol_01`. */
export const paperCollectionReadFixture: PaperCollectionReadDto = {
  artifact_version_id: "artv_papcol_01",
  artifact_id: "art_papcol_01",
  project_id: "proj_01JEXAMPLE",
  source_mode: "fixture",
  content_hash: hash("1"),
  input_hash: hash("2"),
  created_at: T_FINISHED,
  collection: {
    schema_version: "1.0.0",
    query: {
      query_id: "pq_01",
      original_query_string: "TOI-1234 host star parameters",
      normalized_query_string: "toi-1234 host star parameters",
      original_keywords: ["TOI-1234", "host star parameters"],
      normalized_keywords: ["toi-1234", "host star parameters"],
      year_from: 2018,
      year_to: 2026,
      source_ids: ["nasa_ads", "arxiv"],
      source_parameters: { nasa_ads: {}, arxiv: {} },
      sort_strategy: "relevance_desc",
      pagination,
      normalization_rule_version: "1.0.0",
      query_hash: hash("d"),
    },
    acquisition_run: {
      acquisition_id: "pacq_01",
      status: "completed",
      started_at: T_STARTED,
      finished_at: T_FINISHED,
      candidate_count: 4,
      selected_count: 2,
      duplicate_group_count: 3,
      source_failure_count: 0,
    },
    benchmark: {
      benchmark_id: "exoplanet_host_star.paper_acquisition",
      benchmark_version: "1.3.0",
      scenario_id: "search.tess_mission_and_catalogs",
      schema_version: "1.3.0",
      scientific_payload_hash: hash("a"),
      content_hash: hash("b"),
      x00_main_sha: "eb7e23f6d0c14555627c602c6e5a2b84210ba833",
    },
    metrics: {
      candidate_count: 4,
      selected_count: 2,
      duplicate_candidate_count: 1,
      duplicate_rate: 0.25,
      expected_candidate_count: 2,
      recalled_expected_candidate_count: 2,
      candidate_recall: 1,
      source_execution_count: 2,
      source_failure_count: 0,
      source_empty_result_count: 0,
    },
    rules: {
      adapter_name: "paper_acquisition",
      adapter_version: "1.0.0",
      query_normalization_version: "1.0.0",
      canonicalization_version: "1.0.0",
      dedupe_version: "1.0.0",
      ranking_version: "1.0.0",
      selection_version: "1.0.0",
      selection_limit: 3,
      retry_policy_version: "1.0.0",
      source_policy_version: "1.0.0",
    },
    dedupe_rule: "doi_arxiv_title_v1",
    ranking_rule: "relevance_desc_v1",
    source_executions: [
      {
        source_id: "nasa_ads",
        source_mode: "fixture",
        data_level: "fixture",
        status: "completed",
        failure_class: null,
        failure_code: null,
        candidate_count: 2,
        retry_count: 0,
        started_at: T_STARTED,
        finished_at: T_RETRIEVED,
        query_hash: hash("d"),
        request_parameters_hash: hash("e"),
        source_snapshot_id: "snap_paper_ads_01",
        pagination,
        pages: [
          {
            page_number: 1,
            offset: 0,
            requested_rows: 50,
            returned_rows: 2,
            status_code: 200,
            attempt_count: 1,
            request_hash: hash("e"),
            response_hash: hash("4"),
            retrieved_at: T_RETRIEVED,
            total_results: 2,
            rate_limit_metadata: {},
          },
        ],
      },
      {
        source_id: "arxiv",
        source_mode: "fixture",
        data_level: "fixture",
        status: "completed",
        failure_class: null,
        failure_code: null,
        candidate_count: 2,
        retry_count: 1,
        started_at: T_STARTED,
        finished_at: T_RETRIEVED,
        query_hash: hash("d"),
        request_parameters_hash: hash("f"),
        source_snapshot_id: "snap_paper_arxiv_01",
        pagination,
        pages: [
          {
            page_number: 1,
            offset: 0,
            requested_rows: 50,
            returned_rows: 2,
            status_code: 200,
            attempt_count: 2,
            request_hash: hash("f"),
            response_hash: hash("5"),
            retrieved_at: T_RETRIEVED,
            total_results: 2,
            rate_limit_metadata: { retry_after_seconds: 30 },
          },
        ],
      },
    ],
    candidates: [...candidates],
    duplicate_groups: [...duplicateGroups],
    potential_duplicates: [],
    selected_paper_ids: ["paper_01", "paper_02"],
    source_snapshot_ids: ["snap_paper_ads_01", "snap_paper_arxiv_01"],
    producer: {
      execution_id: "pexec_papcol_01",
      run_id: null,
      step_key: "searching_papers",
      producer_type: "algorithm",
      producer_name: "xingwen.paper_acquisition",
      producer_version: "1.0.0",
      model_name: null,
      prompt_name: null,
      prompt_version: null,
      parameters_hash: hash("e"),
      input_hash: hash("2"),
      output_hash: hash("1"),
      status: "completed",
      started_at: T_STARTED,
      finished_at: T_FINISHED,
      latency_ms: 1200,
      error_code: null,
    },
    input_hash: hash("2"),
    output_hash: hash("1"),
  },
  producer_execution: {
    id: "pexec_run_papcol_01",
    run_id: "run_01JEXAMPLE",
    step_key: "searching_papers",
    step_attempt_id: "att_papcol_01",
    producer: {
      type: "pipeline",
      name: "data",
      version: "1.0.0",
      model_name: null,
      prompt_name: null,
      prompt_version: null,
      parameters_hash: null,
    },
    parameters: {},
    parameters_hash: hash("e"),
    input_hash: hash("2"),
    output_hash: hash("1"),
    status: "completed",
    started_at: T_STARTED,
    finished_at: T_FINISHED,
    token_usage: null,
    latency_ms: 1200,
    error_code: null,
  },
  source_snapshots: [adsSnapshot, arxivSnapshot],
  evidence: [...evidence],
};

/** Candidate reads in the authoritative server ranking order. */
export const paperCandidateReadsFixture: readonly PaperCollectionCandidateReadDto[] =
  candidates.map((candidate, index) => ({
    candidate,
    duplicate_group: duplicateGroups.find(
      (group) => group.duplicate_group_id === candidate.duplicate_group_id,
    ) as PaperDuplicateGroupDto,
    source_snapshot:
      candidate.raw.source_snapshot_id === "snap_paper_ads_01"
        ? adsSnapshot
        : arxivSnapshot,
    evidence: [evidence[index] as EvidenceDetailDto],
  }));
