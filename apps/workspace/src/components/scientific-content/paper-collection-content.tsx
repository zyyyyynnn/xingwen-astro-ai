import { safeExternalUrl } from "@xingwen/domain";
import type { PaperAcquisitionReviewViewModel } from "@xingwen/research-adapter";
import { Badge, Link } from "@xingwen/ui";

import {
  limitNote,
  ScientificContentHeader,
  SURFACE_LIMITS,
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
    <div className="scientific-artifact__table-scroll my-3 overflow-x-auto rounded border border-[var(--oh-border)]">
      <table className="w-full border-collapse text-left text-xs">
        <caption className="sr-only">论文候选与筛选结果</caption>
        <thead>
          <tr className="border-b border-[var(--oh-border)] bg-[var(--oh-surface-subtle)]">
            <th scope="col" className="p-2.5 font-medium">
              状态
            </th>
            <th scope="col" className="p-2.5 font-medium">
              论文
            </th>
            <th scope="col" className="p-2.5 font-medium">
              作者 / 年份
            </th>
            <th scope="col" className="p-2.5 font-medium">
              DOI / arXiv
            </th>
            <th scope="col" className="p-2.5 font-medium">
              筛选说明
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--oh-border)]">
          {candidates.map((candidate) => {
            const safeUrl = safeExternalUrl(candidate.url);
            const duplicateCount = candidate.duplicateGroup.candidateIds.length;
            return (
              <tr key={candidate.candidateId}>
                <td className="p-2.5 align-top font-medium text-[var(--oh-foreground)]">
                  {candidate.selection.kind === "selected"
                    ? "已选用"
                    : "未选用"}
                </td>
                <td className="p-2.5 align-top">
                  {safeUrl ? (
                    <Link
                      href={safeUrl}
                      external
                      className="font-serif text-sm font-medium leading-5 text-inherit hover:underline"
                    >
                      {candidate.title || "未提供标题"}
                    </Link>
                  ) : (
                    <span className="font-serif text-sm font-medium leading-5">
                      {candidate.title || "未提供标题"}
                    </span>
                  )}
                  <div className="mt-1 text-xs text-[var(--oh-muted)]">
                    相关度 {candidate.relevanceScore.toFixed(2)}
                    {duplicateCount > 1
                      ? ` · 重复候选 ${duplicateCount} 项`
                      : ""}
                    {candidate.conflicts.length > 0
                      ? ` · 检测到 ${candidate.conflicts.length} 项来源冲突`
                      : ""}
                  </div>
                </td>
                <td className="p-2.5 align-top">
                  <div>
                    {candidate.authors.slice(0, 2).join("、") || "未提供作者"}
                  </div>
                  <div className="mt-1 text-xs text-[var(--oh-muted)]">
                    {candidate.year ?? "年份未提供"}
                  </div>
                </td>
                <td className="p-2.5 align-top">
                  <div>{candidate.doi ?? candidate.arxivId ?? "未提供"}</div>
                  {candidate.doi && candidate.arxivId ? (
                    <div className="mt-1 text-xs text-[var(--oh-muted)]">
                      {candidate.arxivId}
                    </div>
                  ) : null}
                </td>
                <td className="p-2.5 align-top text-[var(--oh-muted)]">
                  {candidate.selection.reason || "未提供筛选说明"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {limitNote(review.candidates.length, candidates.length, "篇候选论文") ? (
        <p className="border-t border-[var(--oh-border)] bg-[var(--oh-surface-subtle)] p-2 text-xs text-[var(--oh-muted)]">
          {limitNote(review.candidates.length, candidates.length, "篇候选论文")}
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
                  {review.metrics.sourceFailureCount} 个来源获取失败
                </Badge>,
              ]
            : []
        }
      />
      <div
        className="scientific-artifact__summary my-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-[var(--oh-muted)]"
        aria-label="论文集合摘要"
      >
        <span>检索词：{review.query.normalizedQuery}</span>
        <span>候选 {review.metrics.candidateCount} 篇</span>
        <span>已选 {review.metrics.selectedCount} 篇</span>
      </div>
      {review.candidates.length > 0 ? (
        <PaperCandidateTable review={review} surface={surface} />
      ) : (
        <p className="py-6 text-center text-xs text-[var(--oh-muted)]">
          当前结果没有可展示的论文候选。
        </p>
      )}
    </article>
  );
}
