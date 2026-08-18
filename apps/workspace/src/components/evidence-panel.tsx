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
      <div className={`p-4 text-xs text-muted-foreground ${className}`}>
        暂无相关引文证据。
      </div>
    );
  }

  return (
    <div
      className={`xw-evidence-panel flex flex-col gap-3 ${className}`}
      data-testid="evidence-panel"
    >
      {title && (
        <h4 className="text-xs font-semibold text-foreground">{title}</h4>
      )}
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
            <div
              key={item.evidenceId}
              className="xw-evidence-item rounded-lg border border-border/60 bg-muted/20 p-3 text-xs"
            >
              {item.quoteOrValue && (
                <div className="mb-2 flex items-start gap-2 text-foreground">
                  <Quote
                    className="size-3.5 shrink-0 text-muted-foreground mt-0.5"
                    aria-hidden="true"
                  />
                  <blockquote className="italic font-serif leading-relaxed">
                    "{item.quoteOrValue}"
                  </blockquote>
                </div>
              )}

              <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-muted-foreground">
                <span className="font-medium">{locationString}</span>
                {locator.sourceUrl && (
                  <Link
                    href={locator.sourceUrl}
                    external
                    className="inline-flex items-center gap-1 font-medium text-primary hover:underline"
                  >
                    <span>查看原文依据</span>
                    <ExternalLink className="size-3" aria-hidden="true" />
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
