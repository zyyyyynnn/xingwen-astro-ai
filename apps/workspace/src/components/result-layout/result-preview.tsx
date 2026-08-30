import type { DomainEntityId } from "@xingwen/domain";
import {
  Badge,
  Button,
  Item,
  ItemActions,
  ItemContent,
  ItemDescription,
  ItemTitle,
} from "@xingwen/ui";
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
    <Item
      className={`xw-result-preview ${isReviewState ? "xw-result-preview--review" : ""} ${className}`}
      variant="default"
      size="default"
      data-testid={`artifact-result-${versionId}`}
      data-kind={kind}
    >
      <ItemContent>
        <div className="xw-result-preview__meta">
          {kindLabel ? <span>{kindLabel}</span> : null}
          {statusLabel ? (
            <Badge variant={statusVariant}>{statusLabel}</Badge>
          ) : null}
        </div>
        <ItemTitle>{title}</ItemTitle>
        {facts ? (
          <ItemDescription>{facts}</ItemDescription>
        ) : summary ? (
          <ItemDescription>{summary}</ItemDescription>
        ) : null}
      </ItemContent>

      {onOpen ? (
        <ItemActions>
          <Button
            size="small"
            variant={isReviewState ? "secondary" : "ghost"}
            onClick={onOpen}
            aria-label={`${actionLabel}：${title}`}
          >
            <span>{actionLabel}</span>
            <ArrowRight data-icon="inline-end" aria-hidden="true" />
          </Button>
        </ItemActions>
      ) : null}
    </Item>
  );
}
