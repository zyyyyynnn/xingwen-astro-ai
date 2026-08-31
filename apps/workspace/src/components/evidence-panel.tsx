import type { PaperSummaryEvidenceReview } from "@xingwen/domain";
import { Link } from "@xingwen/ui";
import { ExternalLink, Quote } from "@xingwen/ui/icons";

export interface EvidencePanelProps {
  readonly evidence: readonly PaperSummaryEvidenceReview[];
  readonly title?: string;
  readonly className?: string;
}

export function EvidencePanel({
  evidence,
  title = "支持证据与原文依据",
  className = "",
}: EvidencePanelProps) {
  if (evidence.length === 0) {
    return (
      <div className={`xw-evidence-panel__empty ${className}`}>
        暂无相关引文证据。
      </div>
    );
  }

  return (
    <div
      className={`xw-evidence-panel flex flex-col gap-3 ${className}`}
      data-testid="evidence-panel"
    >
      {title && <h4 className="text-xs font-semibold">{title}</h4>}
      <div className="flex flex-col gap-2.5">
        {evidence.map((item) => {
          const locator = item.locator;
          const locationString =
            locator.kind === "paper_text"
              ? [
                  locator.section,
                  locator.paragraph === null
                    ? null
                    : `第 ${locator.paragraph} 段`,
                  locator.pageIndex === null
                    ? null
                    : `第 ${locator.pageIndex + 1} 页`,
                  locator.textRange,
                ]
                  .filter(Boolean)
                  .join(" · ")
              : `元数据字段：${locator.metadataField}`;

          return (
            <div key={item.evidenceId} className="xw-evidence-item">
              {item.quoteOrValue && (
                <div className="mb-2 flex items-start gap-2">
                  <Quote
                    className="mt-0.5 size-[var(--icon-size-sm)] shrink-0 xw-evidence-item__quote-icon"
                    aria-hidden="true"
                  />
                  <blockquote className="italic font-serif leading-relaxed">
                    "{item.quoteOrValue}"
                  </blockquote>
                </div>
              )}

              <div className="ui-text-label flex flex-wrap items-center justify-between gap-2 xw-evidence-item__locator">
                <span className="font-medium">{locationString}</span>
                {locator.sourceUrl && (
                  <Link
                    href={locator.sourceUrl}
                    external
                    className="inline-flex items-center gap-1 font-medium hover:underline"
                  >
                    <span>查看原文依据</span>
                    <ExternalLink
                      className="size-[var(--icon-size-xs)]"
                      aria-hidden="true"
                    />
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
