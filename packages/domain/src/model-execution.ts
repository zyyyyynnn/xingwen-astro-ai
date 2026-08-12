import type { ContentHash, UtcIsoTimestamp } from "./value-types";
import type { DomainEntityId } from "./identifiers";

export type ModelExecutionStatus =
  "pending" | "running" | "succeeded" | "failed";

export interface ModelExecutionRecord {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly provider: string;
  readonly model: string;
  readonly modelRevision: string;
  readonly promptName: string;
  readonly promptVersion: string;
  readonly promptHash: ContentHash;
  readonly promptSnapshot: string;
  readonly inputHash: ContentHash | null;
  readonly inputSnapshot: Readonly<Record<string, unknown>>;
  readonly outputHash: ContentHash | null;
  readonly outputSnapshot: Readonly<Record<string, unknown>> | null;
  readonly parametersHash: ContentHash;
  readonly parametersSnapshot: Readonly<Record<string, unknown>>;
  readonly status: ModelExecutionStatus;
  readonly tokenUsage: Readonly<Record<string, unknown>> | null;
  readonly latencyMs: number | null;
  readonly providerRequestId: string | null;
  readonly errorCode: string | null;
  readonly errorSummary: string | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly finishedAt: UtcIsoTimestamp | null;
}
