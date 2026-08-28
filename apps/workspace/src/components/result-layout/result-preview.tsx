import type { DomainEntityId } from "@xingwen/domain";
import { Badge, Button } from "@xingwen/ui";
import {
  Activity,
  ArrowRight,
  BrainCircuit,
  Database,
  FileCheck2,
  FileText,
  ListChecks,
} from "@xingwen/ui/icons";

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

function ResultKindIcon({
  kind,
  className,
}: {
  readonly kind?: string;
  readonly className?: string;
}) {
  switch (kind) {
    case "dataset":
    case "field_dictionary":
    case "source_collection":
      return <Database className={className} aria-hidden="true" />;
    case "paper_summary":
    case "paper_collection":
      return <FileText className={className} aria-hidden="true" />;
    case "literature_claims":
    case "literature_relations":
      return <ListChecks className={className} aria-hidden="true" />;
    case "graph":
      return <BrainCircuit className={className} aria-hidden="true" />;
    case "analysis_report":
    case "visualization":
    case "model_evaluation":
    case "model_artifact":
    case "spectrum":
    case "light_curve":
      return <Activity className={className} aria-hidden="true" />;
    default:
      return <FileCheck2 className={className} aria-hidden="true" />;
  }
}

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
  return (
    <div
      className={`xw-result-preview my-2.5 rounded-lg border border-border/80 bg-surface p-3.5 transition-colors hover:border-border hover:bg-surface-hover/40 ${className}`}
      data-testid={`artifact-result-${versionId}`}
      data-kind={kind}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md border border-border/60 bg-surface-muted text-muted-foreground">
            <ResultKindIcon kind={kind} className="size-4" />
          </div>

          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {kindLabel ? (
                <span className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
                  {kindLabel}
                </span>
              ) : null}
              {statusLabel ? (
                <Badge variant={statusVariant} className="h-4 px-1 text-[10px]">
                  {statusLabel}
                </Badge>
              ) : null}
            </div>

            <h3 className="truncate text-sm font-medium text-foreground">
              {title}
            </h3>

            {summary ? (
              <p className="ui-text-label mt-0.5 line-clamp-2 text-muted-foreground">
                {summary}
              </p>
            ) : null}

            {facts ? (
              <p className="font-mono text-xs text-muted-foreground/80 mt-1">
                {facts}
              </p>
            ) : null}
          </div>
        </div>

        {onOpen ? (
          <Button
            size="small"
            variant="ghost"
            className="shrink-0 gap-1 text-xs font-medium text-muted-foreground hover:text-foreground"
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
