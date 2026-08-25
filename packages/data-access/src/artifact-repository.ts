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
  ArtifactVersionSummary,
  Evidence,
  ResearchArtifact,
  SourceSnapshotSummary,
} from "@xingwen/domain";

import { HttpClient, seg, validateAndMap } from "./http-client";
import {
  mapArtifactVersionMetadata,
  mapArtifactVersionSummary,
  mapEvidenceRead,
  mapResearchArtifact,
  mapResearchArtifactDetail,
} from "./mapping";
import type { ArtifactReadRepository } from "./ports";
import { mapSnapshotSummary } from "./paper-acquisition-repository";

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
    async listVersions(artifactId): Promise<readonly ArtifactVersionSummary[]> {
      const payloads = await http.list<unknown>(
        `/api/artifacts/${seg(artifactId)}/versions`,
      );
      return payloads.map((p) =>
        validateAndMap("ArtifactVersionSummary", p, mapArtifactVersionSummary),
      );
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
    async getSourceSnapshot(id): Promise<SourceSnapshotSummary | null> {
      const payload = await http.get<unknown>(
        `/api/source-snapshots/${seg(id)}`,
      );
      return payload
        ? validateAndMap("SourceSnapshotDetail", payload, mapSnapshotSummary)
        : null;
    },
  };
}
