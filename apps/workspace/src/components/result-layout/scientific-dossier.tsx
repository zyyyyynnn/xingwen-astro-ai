import type { ReactNode } from "react";
import { Badge } from "@xingwen/ui";
import {
  ScientificFactGrid,
  type ScientificFactItem,
} from "./scientific-fact-grid";

export interface ScientificDossierProps {
  readonly status?:
    "accepted" | "candidate" | "rejected" | "unresolved" | string | null;
  readonly statusLabel?: string | null;
  readonly category?: string | null;
  readonly title: string;
  readonly statement?: string | null;
  readonly facts?: readonly ScientificFactItem[];
  readonly evidenceActions?: ReactNode;
  readonly actions?: ReactNode;
  readonly children?: ReactNode;
  readonly className?: string;
  readonly testId?: string;
}

function statusBadgeVariant(
  status: string | null | undefined,
): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "accepted":
      return "default";
    case "rejected":
      return "destructive";
    case "candidate":
      return "secondary";
    default:
      return "outline";
  }
}

export function ScientificDossier({
  status,
  statusLabel,
  category,
  title,
  statement,
  facts = [],
  evidenceActions = null,
  actions = null,
  children = null,
  className = "",
  testId,
}: ScientificDossierProps) {
  const displayStatusLabel =
    statusLabel ??
    (status === "accepted"
      ? "已接受"
      : status === "candidate"
        ? "候选"
        : status === "rejected"
          ? "已拒绝"
          : status === "unresolved"
            ? "未解析"
            : status);

  const isCandidate = status === "candidate";
  const isRejected = status === "rejected";

  const surfaceClass = isCandidate
    ? "bg-surface-muted/40 border-border/80"
    : isRejected
      ? "bg-background border-border/40 opacity-75"
      : "bg-background border-border/60";

  return (
    <article
      className={`xw-scientific-dossier flex flex-col gap-3 rounded-md border p-4 transition-colors hover:border-border ${surfaceClass} ${className}`}
      data-status={status ?? undefined}
      data-testid={testId}
    >
      <header className="flex flex-col gap-1.5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            {displayStatusLabel ? (
              <Badge
                variant={statusBadgeVariant(status)}
                className="h-5 px-1.5 text-xs font-normal"
              >
                {displayStatusLabel}
              </Badge>
            ) : null}
            {category ? (
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {category}
              </span>
            ) : null}
          </div>
          {actions ? (
            <div className="flex flex-wrap items-center gap-1.5">{actions}</div>
          ) : null}
        </div>

        <h4 className="font-serif text-base font-semibold leading-snug tracking-tight text-foreground">
          {title}
        </h4>

        {statement && statement !== title ? (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {statement}
          </p>
        ) : null}
      </header>

      {facts.length > 0 ? <ScientificFactGrid facts={facts} /> : null}

      {children}

      {evidenceActions ? (
        <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border/40">
          {evidenceActions}
        </div>
      ) : null}
    </article>
  );
}
