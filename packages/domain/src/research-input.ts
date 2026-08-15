import type { DomainEntityId } from "./identifiers";
import type { UtcIsoTimestamp } from "./value-types";

export type ResearchInputType =
  | "url"
  | "pdf"
  | "csv"
  | "xlsx"
  | "parquet"
  | "json"
  | "image"
  | "image_dataset"
  | "fits"
  | "text";

export type ResearchInputStatus =
  "accepted" | "unsupported_processing" | "failed_ingestion";

/** Metadata-only reference to an ingested project input. */
export interface ResearchInputRef {
  readonly contentHash: string;
  readonly createdAt: UtcIsoTimestamp;
  readonly filename: string | null;
  readonly id: DomainEntityId;
  readonly mimeType: string | null;
  readonly sizeBytes: number;
  readonly sourceSnapshotId: DomainEntityId | null;
  readonly sourceType: string;
  readonly status: ResearchInputStatus | null;
  readonly type: ResearchInputType;
}

export type CreateResearchInput =
  | {
      readonly type: "text";
      readonly projectId: DomainEntityId;
      readonly textContent: string;
      readonly filename?: string | null;
      readonly mimeType?: string | null;
      readonly idempotencyKey: string;
    }
  | {
      readonly type: "url";
      readonly projectId: DomainEntityId;
      readonly url: string;
      readonly filename?: string | null;
      readonly mimeType?: string | null;
      readonly idempotencyKey: string;
    }
  | {
      readonly type:
        | "pdf"
        | "csv"
        | "xlsx"
        | "parquet"
        | "json"
        | "image"
        | "image_dataset"
        | "fits";
      readonly projectId: DomainEntityId;
      readonly content: ArrayBuffer;
      readonly filename: string;
      readonly mimeType?: string | null;
      readonly idempotencyKey: string;
    };

export type CreateResearchInputDraft =
  | Omit<
      Extract<CreateResearchInput, { readonly type: "text" }>,
      "idempotencyKey"
    >
  | Omit<
      Extract<CreateResearchInput, { readonly type: "url" }>,
      "idempotencyKey"
    >
  | Omit<
      Extract<
        CreateResearchInput,
        {
          readonly type:
            | "pdf"
            | "csv"
            | "xlsx"
            | "parquet"
            | "json"
            | "image"
            | "image_dataset"
            | "fits";
        }
      >,
      "idempotencyKey"
    >;
