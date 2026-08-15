import { safeExternalUrl } from "@xingwen/domain";
import type { PaperAcquisitionReviewViewModel } from "@xingwen/research-adapter";
import { Badge, Link } from "@xingwen/ui";

import {
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
  sourceModeLabel,
  valueOrUnavailable,
  type ScientificContentSurface,
} from "./shared";

export type PaperCollectionReviewViewModel = PaperAcquisitionReviewViewModel & {
  readonly kind: "paper_collection";
};

function PaperCandidateTable({
  review,
  surface,
}: {
  readonly review: PaperCollectionReviewViewModel;
  readonly surface: ScientificContentSurface;
}) {
  const candidates = review.candidates.slice(0, SURFACE_LIMITS[surface]);
  return (
    <div className="scientific-artifact__table-scroll">
      <table className="scientific-artifact__table">
        <caption className="sr-only">论文候选与筛选结果</caption>
        <thead>
          <tr>
            <th scope="col">排名 / 选择</th>
            <th scope="col">论文</th>
            <th scope="col">作者 / 年</th>
            <th scope="col">标识</th>
            <th scope="col">相关性</th>
            <th scope="col">重复 / 冲突</th>
          </tr>
        </thead>
        <tbody>
          {candidates.map((candidate) => {
            const safeUrl = safeExternalUrl(candidate.url);
            return (
              <tr key={candidate.candidateId}>
                <th scope="row">
                  <span>#{candidate.stableRank}</span>
                  <small>
                    {candidate.selection.kind === "selected" ? "已选" : "未选"}
                  </small>
                </th>
                <td>
                  {safeUrl ? (
                    <Link href={safeUrl} external>
                      {candidate.title || "未提供标题"}
                    </Link>
                  ) : (
                    candidate.title || "未提供标题"
                  )}
                  {candidate.selection.reason ? (
                    <small>{candidate.selection.reason}</small>
                  ) : null}
                </td>
                <td>
                  <span>
                    {candidate.authors.slice(0, 2).join("、") || "未提供作者"}
                  </span>
                  <small>{candidate.year ?? "年份未提供"}</small>
                </td>
                <td>
                  <span>
                    {candidate.doi ?? candidate.arxivId ?? "未提供 DOI / arXiv"}
                  </span>
                  {candidate.doi && candidate.arxivId ? (
                    <small>{candidate.arxivId}</small>
                  ) : null}
                </td>
                <td>{candidate.relevanceScore.toFixed(3)}</td>
                <td>
                  <span>
                    {candidate.duplicateGroup.candidateIds.length > 1
                      ? "重复组"
                      : "单项组"}
                  </span>
                  <small>
                    {candidate.conflicts.length > 0
                      ? `冲突 ${candidate.conflicts.length}`
                      : "无冲突"}
                  </small>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {limitNote(review.candidates.length, candidates.length, "条候选") ? (
        <p className="scientific-artifact__table-note">
          {limitNote(review.candidates.length, candidates.length, "条候选")}
        </p>
      ) : null}
    </div>
  );
}

export function PaperCollectionContent({
  review,
  title,
  surface,
}: {
  readonly review: PaperCollectionReviewViewModel;
  readonly title: string;
  readonly surface: ScientificContentSurface;
}) {
  return (
    <article
      className="scientific-artifact scientific-artifact--paper-collection"
      data-surface={surface}
    >
      <ScientificContentHeader
        title={title}
        subtitle="论文集合"
        alerts={
          review.metrics.sourceFailureCount > 0
            ? [
                <Badge key="failures" variant="destructive">
                  来源失败 {review.metrics.sourceFailureCount}
                </Badge>,
              ]
            : []
        }
      />
      <div className="scientific-artifact__summary" aria-label="论文集合摘要">
        <span>查询：{review.query.normalizedQuery}</span>
        <span>候选 {review.metrics.candidateCount} 篇</span>
        <span>已选 {review.metrics.selectedCount} 篇</span>
        <span>重复候选 {review.metrics.duplicateCandidateCount}</span>
        <span>召回 {valueOrUnavailable(review.metrics.candidateRecall)}</span>
        <span>{sourceModeLabel(review.sourceMode)}</span>
      </div>
      {review.candidates.length > 0 ? (
        <PaperCandidateTable review={review} surface={surface} />
      ) : (
        <p className="scientific-artifact__empty">
          当前版本没有可展示的论文候选。
        </p>
      )}
    </article>
  );
}
