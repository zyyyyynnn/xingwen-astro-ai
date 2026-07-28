/**
 * Candidate review list — semantic ordered list of paper candidates in the
 * authoritative server ranking order. Filters only hide rows; every visible
 * row keeps its original `stableRank`. External URLs render as links only
 * when http(s)-safe; everything else stays plain text.
 */

import type { Evidence, PaperCandidateReview } from "@xingwen/domain";
import { safeExternalUrl } from "@xingwen/domain";

import { hasConflicts, isDuplicateCandidate } from "./paper-acquisition-state";

export interface CandidateReviewListProps {
  readonly candidates: readonly PaperCandidateReview[];
  readonly selectedCandidateId: string | null;
  readonly disabled: boolean;
  readonly onSelectCandidate: (candidate: PaperCandidateReview) => void;
  readonly onSelectEvidence: (evidence: Evidence) => void;
}

function ExternalReference({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}) {
  const safeUrl = safeExternalUrl(value);
  return (
    <span className="candidate-meta-item">
      {label}:{" "}
      {safeUrl ? (
        <a href={safeUrl} target="_blank" rel="noreferrer noopener">
          {safeUrl}
        </a>
      ) : (
        value
      )}
    </span>
  );
}

export function CandidateReviewList({
  candidates,
  selectedCandidateId,
  disabled,
  onSelectCandidate,
  onSelectEvidence,
}: CandidateReviewListProps) {
  if (candidates.length === 0) {
    return <p aria-live="polite">没有匹配当前筛选的候选。</p>;
  }
  return (
    <ol className="candidate-list" aria-label="候选论文">
      {candidates.map((candidate) => {
        const isSelected =
          selectedCandidateId === String(candidate.candidateId);
        return (
          <li
            key={String(candidate.candidateId)}
            className="candidate-item"
            aria-current={isSelected ? "true" : undefined}
          >
            <div className="candidate-head">
              <span className="candidate-rank">#{candidate.stableRank}</span>
              <button
                type="button"
                className="candidate-select"
                aria-pressed={isSelected}
                onClick={() => onSelectCandidate(candidate)}
                disabled={disabled}
              >
                {candidate.title}
              </button>
              <span className="candidate-status">
                {candidate.selection.kind === "selected" ? "入选" : "排除"}
              </span>
            </div>
            <p className="candidate-meta">
              <span className="candidate-meta-item">
                {candidate.authors.length > 0
                  ? candidate.authors.join("、")
                  : "作者未知"}
              </span>
              <span className="candidate-meta-item">
                {candidate.year ?? "年份未知"}
              </span>
              <span className="candidate-meta-item">
                relevance {candidate.relevanceScore}
              </span>
            </p>
            <p className="candidate-meta">
              {candidate.doi !== null && (
                <span className="candidate-meta-item">
                  DOI: {candidate.doi}
                </span>
              )}
              {candidate.arxivId !== null && (
                <span className="candidate-meta-item">
                  arXiv: {candidate.arxivId}
                </span>
              )}
              {candidate.url !== null && (
                <ExternalReference label="URL" value={candidate.url} />
              )}
              <span className="candidate-meta-item">
                来源: {String(candidate.sourceSnapshot.sourceId)}
              </span>
            </p>
            <p className="candidate-reason">
              {candidate.selection.kind === "selected"
                ? `入选原因：${candidate.selection.reason ?? "未提供"}`
                : `排除原因：${candidate.selection.reason ?? "未提供"}`}
            </p>
            {isDuplicateCandidate(candidate) && (
              <p className="candidate-meta">
                <span className="candidate-meta-item">
                  重复组 {String(candidate.duplicateGroup.groupId)}（
                  {candidate.duplicateGroup.candidateIds.length} 项，依据{" "}
                  {candidate.duplicateGroup.matchBasis.join("、")}）
                </span>
              </p>
            )}
            {hasConflicts(candidate) && (
              <ul className="candidate-conflicts">
                {candidate.duplicateGroup.conflicts.map((conflict) => (
                  <li
                    key={`${String(candidate.duplicateGroup.groupId)}-${conflict.field}-${String(conflict.relatedCandidateId)}`}
                  >
                    {conflict.classification === "conflict"
                      ? "冲突"
                      : "不确定匹配"}
                    （{conflict.field}）：{conflict.detail}
                  </li>
                ))}
              </ul>
            )}
            {isSelected && candidate.evidence.length > 0 && (
              <div className="action-row">
                {candidate.evidence.map((item) => (
                  <button
                    key={String(item.id)}
                    type="button"
                    onClick={() => onSelectEvidence(item)}
                    disabled={disabled}
                  >
                    打开 Evidence {String(item.id)}
                  </button>
                ))}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
