import type { ResearchContractInput } from "@xingwen/domain";

/**
 * The seed contract input a freshly created draft starts from.
 *
 * It mirrors the frozen exoplanet host-star main case so a new draft is
 * immediately valid against the contract invariants; the Guided Tour lets the
 * researcher edit the intent and research goal before confirming. This is the
 * single source used by both the fixture and HTTP chains, so `createDraft`
 * behaves identically across adapters.
 */
export const NEW_DRAFT_CONTRACT_INPUT: ResearchContractInput = {
  researchGoal:
    "Integrate exoplanet candidates and host-star parameters" as ResearchContractInput["researchGoal"],
  targetObjects: [
    "exoplanet_candidate",
    "host_star",
  ] as unknown as ResearchContractInput["targetObjects"],
  dataRequirements: { unitPolicy: "canonical" },
  requestedFields: [
    "planet.toi_id",
    "star.tic_id",
  ] as unknown as ResearchContractInput["requestedFields"],
  sourceScope: {
    allowedSources: [
      "nasa_exoplanet_archive",
    ] as unknown as ResearchContractInput["sourceScope"]["allowedSources"],
  },
  paperSearchScope: {
    keywords: ["exoplanet", "host star parameters"],
    yearFrom: 2018,
    yearTo: 2026,
    sourceIds: [
      "nasa_exoplanet_archive",
    ] as unknown as ResearchContractInput["paperSearchScope"]["sourceIds"],
    maxCandidates: 5,
  },
  outputRequirements: [
    "dataset",
    "graph",
  ] as unknown as ResearchContractInput["outputRequirements"],
  evidenceRequirements: {
    requireLocator: true,
    requireSourceSnapshot: true,
    minimumCoverage: 1,
  },
  qualityConstraints: {
    sourceCompletenessMin: 1,
    unitConsistencyMin: 1,
  },
};
