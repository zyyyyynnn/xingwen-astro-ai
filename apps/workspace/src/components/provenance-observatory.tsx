/**
 * Provenance Observatory — presentation-only right-rail content for the
 * workspace: the selected ArtifactVersion's identity/provenance, the selected
 * Evidence, and (when reviewing a paper collection) the selected candidate's
 * object identity, snapshot, hashes and license note.
 *
 * Evidence gaps are stated explicitly; a candidate is never presented as a
 * verified fact without its Evidence.
 */

import type {
  ArtifactVersionMetadata,
  Evidence,
  PaperCandidateReview,
} from "@xingwen/domain";

export function evidenceSummary(evidence: Evidence): string {
  if (evidence.locator?.kind === "database_cell") {
    return `数据库字段 ${evidence.locator.field}`;
  }
  if (evidence.locator?.kind === "paper_text") {
    return `论文 ${evidence.locator.section}`;
  }
  if (evidence.locator?.kind === "reasoning_trace") {
    return `推理步骤 ${evidence.locator.stepKey}`;
  }
  if (evidence.locator?.kind === "model_extraction") {
    return `提取 ${evidence.locator.promptName}`;
  }
  return "无 locator";
}

export interface ProvenanceObservatoryProps {
  readonly version: ArtifactVersionMetadata | null;
  readonly evidence: Evidence | null;
  readonly candidate: PaperCandidateReview | null;
  readonly canAdjust: boolean;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}

export function ProvenanceObservatory({
  version,
  evidence,
  candidate,
  canAdjust,
  onSelectEvidence,
}: ProvenanceObservatoryProps) {
  if (!version) {
    return (
      <p className="region-placeholder">选择 ArtifactVersion 后显示证据。</p>
    );
  }
  const candidateEvidence = candidate?.evidence[0] ?? null;
  return (
    <>
      <p className="region-label">Artifact Version</p>
      <p className="region-placeholder">
        {version.id} / v{version.versionNumber}
      </p>
      <p className="region-placeholder">
        {version.sourceMode} / {version.contentHash}
      </p>
      {candidate && (
        <>
          <p className="region-label">Candidate</p>
          <p className="region-placeholder">
            {candidate.candidateId} / canonical {candidate.canonicalPaperId}
          </p>
          <p className="region-placeholder">
            {candidate.selection.kind === "selected" ? "入选" : "排除"} / rank #
            {candidate.stableRank}
          </p>
          <p className="region-label">Source Snapshot</p>
          <p className="region-placeholder">
            {candidate.sourceSnapshot.id} / {candidate.sourceSnapshot.sourceId}
          </p>
          <p className="region-placeholder">
            retrieved {candidate.sourceSnapshot.retrievedAt}
          </p>
          <p className="region-placeholder">
            query {candidate.sourceSnapshot.queryHash}
          </p>
          <p className="region-placeholder">
            content {candidate.sourceSnapshot.contentHash}
          </p>
          <p className="region-placeholder">
            etag/version {candidate.sourceSnapshot.sourceVersionOrEtag ?? "无"}
          </p>
          <p className="region-placeholder">
            license: {candidate.sourceSnapshot.licenseNote}
          </p>
          <p className="region-label">Candidate Evidence</p>
          {candidateEvidence ? (
            <>
              <button
                type="button"
                className="atlas-item"
                onClick={() => onSelectEvidence(candidateEvidence)}
                disabled={!canAdjust}
              >
                {candidateEvidence.id}
              </button>
              <p className="region-placeholder">
                {evidenceSummary(candidateEvidence)}
              </p>
              <p className="region-placeholder">
                {candidateEvidence.quoteOrValue ?? "无公开值"}
              </p>
              <p className="region-placeholder">
                {candidateEvidence.extractionMethod} / confidence{" "}
                {candidateEvidence.confidence}
              </p>
            </>
          ) : (
            <p className="region-placeholder">
              该候选缺少 Evidence，不能视为已验证事实。
            </p>
          )}
        </>
      )}
      {evidence && (
        <>
          <p className="region-label">Evidence</p>
          <button
            type="button"
            className="atlas-item"
            onClick={() => onSelectEvidence(evidence)}
            disabled={!canAdjust}
          >
            {evidence.id}
          </button>
          <p className="region-placeholder">{evidenceSummary(evidence)}</p>
        </>
      )}
    </>
  );
}
