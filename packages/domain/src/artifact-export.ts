import type { DomainEntityId } from "./identifiers";
import type { ContentHash, UtcIsoTimestamp } from "./value-types";

export type ArtifactExportFormat = "csv" | "json" | "provenance_report";

export interface ArtifactExport {
  readonly id: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly format: ArtifactExportFormat;
  readonly status: "completed" | "expired";
  readonly contentHash: ContentHash;
  readonly generatedAt: UtcIsoTimestamp;
  readonly expiresAt: UtcIsoTimestamp;
  readonly downloadUrl: string | null;
}

export interface ArtifactExportDownload {
  readonly bytes: ArrayBuffer;
  readonly fileName: string;
  readonly mediaType: string;
}
