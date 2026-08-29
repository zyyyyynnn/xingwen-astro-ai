import type { DomainEntityId } from "@xingwen/domain";
import { Badge, Button } from "@xingwen/ui";
import { ArrowRight } from "@xingwen/ui/icons";

export interface ResultPreviewProps {
  readonly artifactId?: DomainEntityId;
  readonly versionId: DomainEntityId;
  readonly kind?: string;
  readonly kindLabel?: string;
  readonly title: string;
  readonly summary?: string | null;
  readonly facts?: string | null;
  readonly statusLabel?: string | null;
  readonly statusVariant?: "default" | "secondary" | "destructive" | "outline";
  readonly onOpen?: (() => void) | null;
  readonly actionLabel?: string;
  readonly className?: string;
}

/**
 * Thread attachment row. Normal completed results stay typographic —
 * spacing and a separator carry the structure, no card chrome. Only
 * review/failed states may take a visible surface.
 */
export function ResultPreview({
  versionId,
  kind,
  kindLabel,
  title,
  summary,
  facts,
  statusLabel,
  statusVariant = "secondary",
  onOpen,
  actionLabel = "查看完整结果",
  className = "",
}: ResultPreviewProps) {
  const isReviewState = statusLabel !== null && statusLabel !== undefined;
  return (
    <div
      className={`xw-result-preview group my-2 px-2 py-2 transition-colors hover:bg-surface-hover/50 ${
        isReviewState ? "bg-surface-muted/60" : ""
      } ${className}`}
      data-testid={`artifact-result-${versionId}`}
      data-kind={kind}
    >
      <div className="flex items-baseline justify-between gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {kindLabel ? (
              <span className="ui-text-label uppercase tracking-wider text-muted-foreground">
                {kindLabel}
              </span>
            ) : null}
            {statusLabel ? (
              <Badge
                variant={statusVariant}
                className="h-4 px-1 text-[length:var(--font-size-00)]"
              >
                {statusLabel}
              </Badge>
            ) : null}
          </div>
          <h3 className="mt-0.5 truncate text-sm font-medium text-foreground">
            {title}
          </h3>
          {facts ? (
            <p className="mt-0.5 truncate text-xs text-muted-foreground">
              {facts}
            </p>
          ) : summary ? (
            <p className="mt-0.5 line-clamp-2 text-xs text-muted-foreground">
              {summary}
            </p>
          ) : null}
        </div>

        {onOpen ? (
          <Button
            size="small"
            variant="ghost"
            className="shrink-0 gap-1 text-xs font-medium text-muted-foreground opacity-80 transition-opacity group-hover:opacity-100 hover:text-foreground"
            onClick={onOpen}
          >
            <span>{actionLabel}</span>
            <ArrowRight className="size-3.5" aria-hidden="true" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}
