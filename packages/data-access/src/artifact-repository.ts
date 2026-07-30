/**
 * Generic Artifact/Evidence read repository over `/api`.
 *
 * Reads are validated against the exact response contract: list items as
 * `ResearchArtifact`, single artifact/version as the richer `*Detail`
 * projections, and Evidence as `EvidenceRead` (the endpoint exists in the
 * runtime, so this is a real read rather than a capability gap).
 */

import type {
  ArtifactVersionMetadata,
  Evidence,
  ResearchArtifact,
} from "@xingwen/domain";

import { HttpClient, seg, validateAndMap } from "./http-client";
import {
  mapArtifactVersionMetadata,
  mapEvidenceRead,
  mapResearchArtifact,
  mapResearchArtifactDetail,
} from "./mapping";
import type { ArtifactReadRepository } from "./ports";

export function createArtifactRepository(
  http: HttpClient,
): ArtifactReadRepository {
  return {
    async listByRun(runId): Promise<readonly ResearchArtifact[]> {
      const payloads = await http.list<unknown>(
        `/api/runs/${seg(runId)}/artifacts`,
      );
      return payloads.map((p) =>
        validateAndMap("ResearchArtifact", p, mapResearchArtifact),
      );
    },
    async getArtifact(id): Promise<ResearchArtifact | null> {
      const payload = await http.get<unknown>(`/api/artifacts/${seg(id)}`);
      return payload
        ? validateAndMap(
            "ResearchArtifactDetail",
            payload,
            mapResearchArtifactDetail,
          )
        : null;
    },
    async getVersion(id): Promise<ArtifactVersionMetadata | null> {
      const payload = await http.get<unknown>(
        `/api/artifact-versions/${seg(id)}`,
      );
      return payload
        ? validateAndMap(
            "ArtifactVersionDetail",
            payload,
            mapArtifactVersionMetadata,
          )
        : null;
    },
    async getEvidence(id): Promise<Evidence | null> {
      const payload = await http.get<unknown>(`/api/evidence/${seg(id)}`);
      return payload
        ? validateAndMap("EvidenceRead", payload, mapEvidenceRead)
        : null;
    },
  };
}
