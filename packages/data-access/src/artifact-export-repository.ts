import type { ArtifactExportRead as ArtifactExportReadDto } from "@xingwen/contracts";
import {
  asEntityId,
  type ArtifactExport,
  type ArtifactExportDownload,
  type DomainEntityId,
} from "@xingwen/domain";

import {
  HttpClient,
  seg,
  stableIdempotencyKey,
  validateAndMap,
} from "./http-client";
import type { ArtifactExportRepository } from "./ports";

function mapExport(dto: ArtifactExportReadDto): ArtifactExport {
  return {
    id: asEntityId(dto.id),
    artifactVersionId: asEntityId(dto.artifact_version_id),
    projectId: asEntityId(dto.project_id),
    format: dto.format,
    status: dto.status,
    contentHash: dto.content_hash,
    generatedAt: dto.generated_at,
    expiresAt: dto.expires_at,
    downloadUrl: dto.download_url ?? null,
  };
}

function parseExport(payload: unknown): ArtifactExport {
  return validateAndMap<ArtifactExportReadDto, ArtifactExport>(
    "ArtifactExportRead",
    payload,
    mapExport,
  );
}

function downloadMetadata(exportRecord: ArtifactExport): {
  readonly fileName: string;
  readonly mediaType: string;
} {
  if (exportRecord.format === "csv") {
    return {
      fileName: `${exportRecord.artifactVersionId}.csv`,
      mediaType: "text/csv; charset=utf-8",
    };
  }
  return {
    fileName:
      exportRecord.format === "provenance_report"
        ? `${exportRecord.artifactVersionId}.provenance.json`
        : `${exportRecord.artifactVersionId}.json`,
    mediaType: "application/json",
  };
}

export function createArtifactExportRepository(
  http: HttpClient,
): ArtifactExportRepository {
  return {
    async create(artifactVersionId, format) {
      const body = { format };
      return parseExport(
        await http.post<unknown>(
          `/api/artifact-versions/${seg(artifactVersionId)}/exports`,
          body,
          {
            "Idempotency-Key": stableIdempotencyKey(
              `artifact-export-${artifactVersionId}`,
              body,
            ),
          },
        ),
      );
    },
    async get(exportId) {
      return parseExport(
        await http.getRequired<unknown>(`/api/exports/${seg(exportId)}`),
      );
    },
    async download(exportRecord) {
      const metadata = downloadMetadata(exportRecord);
      return {
        ...metadata,
        bytes: await http.getArrayBuffer(
          `/api/exports/${seg(exportRecord.id)}/download`,
        ),
      };
    },
  };
}

export function createFixtureArtifactExportRepository(
  projectId: DomainEntityId,
): ArtifactExportRepository {
  const records = new Map<DomainEntityId, ArtifactExport>();
  return {
    async create(artifactVersionId, format) {
      const id = asEntityId(`exp_fixture_${format}`);
      const record: ArtifactExport = {
        id,
        artifactVersionId,
        projectId,
        format,
        status: "completed",
        contentHash: `sha256:${"0".repeat(64)}`,
        generatedAt: "2026-01-01T00:00:00Z",
        expiresAt: "2099-01-01T00:00:00Z",
        downloadUrl: `/api/exports/${id}/download`,
      };
      records.set(id, record);
      return record;
    },
    async get(exportId) {
      const record = records.get(exportId);
      if (!record) throw new Error(`Fixture export ${exportId} not found`);
      return record;
    },
    async download(exportRecord): Promise<ArtifactExportDownload> {
      const metadata = downloadMetadata(exportRecord);
      return {
        ...metadata,
        bytes: new TextEncoder().encode(
          exportRecord.format === "csv"
            ? "Fixture value\ndemo\n"
            : JSON.stringify({
                artifact_version_id: exportRecord.artifactVersionId,
                source_mode: "fixture",
              }),
        ).buffer,
      };
    },
  };
}
