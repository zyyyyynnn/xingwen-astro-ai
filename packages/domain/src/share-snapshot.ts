/**
 * ShareSnapshot and public share projection domain types.
 *
 * Mirrors `ShareSnapshot`, `ShareSnapshotCreated`, `PublicShareSnapshot`,
 * `PublicArtifactVersion` and `PublicEvidence` in the Pydantic `/api`
 * authoring source using frontend camelCase convention.
 *
 * Key security invariants enforced by the adapter:
 * - Raw share tokens only appear in the one-time `ShareSnapshotCreated`
 *   response; private list and public projection never include the token.
 * - `PublicShareSnapshot` is a redacted read-only projection containing only
 *   admitted public Artifact content and Evidence fields; no Project/Session,
 *   producer, binary, execution or private provenance data crosses the boundary.
 * - Invalid, revoked and expired tokens all map to `404 SHARE_NOT_FOUND`.
 *
 * Transport DTO mapping lives in `@xingwen/data-access`.
 */

import type {
  ArtifactKind,
  ShareRedactionPolicy,
  ShareStatus,
  SourceMode,
} from "./enums";
import type { DomainEntityId } from "./identifiers";
import type { JsonValue } from "./research-contract";
import type {
  ContentHash,
  NonEmptyString,
  SemanticVersion,
  UtcIsoTimestamp,
} from "./value-types";

/**
 * Private share metadata. Raw tokens and token hashes are intentionally absent
 * from this type — it represents the list/view record, not the creation
 * response.
 */
export interface ShareSnapshot {
  readonly id: DomainEntityId;
  readonly projectId: DomainEntityId;
  readonly title: NonEmptyString;
  readonly status: ShareStatus;
  readonly redactionPolicy: ShareRedactionPolicy;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly createdAt: UtcIsoTimestamp;
  readonly expiresAt: UtcIsoTimestamp;
  readonly revokedAt: UtcIsoTimestamp | null;
}

/**
 * One-time creation response containing the only serialized raw share token.
 * After this response, the token is never visible again — the private list and
 * public endpoint omit it.
 */
export interface ShareSnapshotCreated extends ShareSnapshot {
  readonly shareToken: string;
  readonly shareUrl: string;
}

/**
 * Request body for creating a new share snapshot.
 */
export interface CreateShareSnapshotRequest {
  readonly title: NonEmptyString;
  readonly artifactVersionIds: readonly DomainEntityId[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly expiresAt: UtcIsoTimestamp;
  readonly redactionPolicy: ShareRedactionPolicy;
}

/**
 * Redacted immutable result projection safe for anonymous presentation. The
 * presentation is the positive-contract scientific view built by the same
 * typed Artifact authority used for private reads.
 */
export interface PublicPresentationFact {
  readonly label: NonEmptyString;
  readonly values: readonly NonEmptyString[];
}

export interface PublicPresentationTrace {
  readonly conclusion: NonEmptyString;
  readonly steps: readonly NonEmptyString[];
  readonly facts: readonly PublicPresentationFact[];
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface PublicPresentationEntry {
  readonly key: NonEmptyString;
  readonly title: NonEmptyString;
  readonly externalUrl: NonEmptyString | null;
  readonly status: NonEmptyString | null;
  readonly assessment: NonEmptyString | null;
  readonly paragraphs: readonly NonEmptyString[];
  readonly facts: readonly PublicPresentationFact[];
  readonly evidenceIds: readonly DomainEntityId[];
  readonly reasoningTrace: PublicPresentationTrace | null;
}

export interface PublicPresentationSection {
  readonly title: NonEmptyString;
  readonly paragraphs: readonly PublicPresentationParagraph[];
}

export interface PublicPresentationTableColumn {
  readonly key: NonEmptyString;
  readonly label: NonEmptyString;
  readonly unit: NonEmptyString | null;
}

export interface PublicPresentationTableCell {
  readonly columnKey: NonEmptyString;
  readonly value: string | null;
  readonly status: "mapped" | "missing" | "unresolved";
  readonly reason: NonEmptyString | null;
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface PublicPresentationTableRow {
  readonly key: NonEmptyString;
  readonly identity: NonEmptyString;
  readonly cells: readonly PublicPresentationTableCell[];
}

export interface PublicPresentationTable {
  readonly title: NonEmptyString;
  readonly columns: readonly PublicPresentationTableColumn[];
  readonly rows: readonly PublicPresentationTableRow[];
  readonly totalRowCount: number;
  readonly totalColumnCount: number;
}

export interface PublicPresentationParagraph {
  readonly text: NonEmptyString;
  readonly status: NonEmptyString | null;
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface PublicPresentationGraphNode {
  readonly key: NonEmptyString;
  readonly kind: NonEmptyString;
  readonly label: NonEmptyString;
}

export interface PublicPresentationGraphEdge {
  readonly key: NonEmptyString;
  readonly kind: NonEmptyString;
  readonly sourceKey: NonEmptyString;
  readonly targetKey: NonEmptyString;
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface PublicArtifactPresentation {
  readonly kind: ArtifactKind;
  readonly summary: NonEmptyString | null;
  readonly facts: readonly PublicPresentationFact[];
  readonly sections: readonly PublicPresentationSection[];
  readonly entries: readonly PublicPresentationEntry[];
  readonly tables: readonly PublicPresentationTable[];
  readonly graphNodes: readonly PublicPresentationGraphNode[];
  readonly graphEdges: readonly PublicPresentationGraphEdge[];
}

export interface PublicArtifactVersion {
  readonly id: DomainEntityId;
  readonly artifactId: DomainEntityId;
  readonly kind: ArtifactKind;
  readonly title: NonEmptyString;
  readonly versionNumber: number;
  readonly schemaVersion: SemanticVersion;
  readonly contentHash: ContentHash;
  readonly sourceMode: SourceMode;
  readonly createdAt: UtcIsoTimestamp;
  readonly presentation: PublicArtifactPresentation;
  readonly evidenceIds: readonly DomainEntityId[];
}

export interface PublicEvidenceBBox {
  readonly x1: number;
  readonly y1: number;
  readonly x2: number;
  readonly y2: number;
}

export interface PublicEvidenceLocator {
  readonly kind: NonEmptyString;
  readonly page: number | null;
  readonly paragraph: number | null;
  readonly section: string | null;
  readonly textRange: string | null;
  readonly field: string | null;
  readonly rowKey: string | null;
  readonly blockId: string | null;
  readonly readingOrder: number | null;
  readonly tableId: string | null;
  readonly cellId: string | null;
  readonly bbox: PublicEvidenceBBox | null;
}

export interface PublicSourceSnapshot {
  readonly sourceId: string;
  readonly sourceType: string;
  readonly retrievedAt: UtcIsoTimestamp;
  readonly licenseNote: string;
  readonly requestMetadata: Readonly<Record<string, JsonValue>>;
}

/**
 * Redacted Evidence detail bound to a shared immutable version. Only source
 * fields needed by the shared inspector survive the public projection.
 */
export interface PublicEvidence {
  readonly id: DomainEntityId;
  readonly artifactVersionId: DomainEntityId;
  readonly sourceSnapshotId: DomainEntityId;
  readonly locator: PublicEvidenceLocator;
  readonly quoteOrValue: string | null;
  readonly createdAt: UtcIsoTimestamp;
  readonly source: PublicSourceSnapshot;
}

/**
 * Anonymous read-only projection frozen when the share is created.
 *
 * This is what the public `GET /api/shares/{share_token}` endpoint returns.
 * It contains only the share metadata and redacted presentation/evidence
 * projections — never private session, producer, binary or execution facts.
 */
export interface PublicShareSnapshot {
  readonly id: DomainEntityId;
  readonly title: NonEmptyString;
  readonly redactionPolicy: ShareRedactionPolicy;
  readonly createdAt: UtcIsoTimestamp;
  readonly expiresAt: UtcIsoTimestamp;
  readonly artifactVersions: readonly PublicArtifactVersion[];
  readonly evidence: readonly PublicEvidence[];
}
