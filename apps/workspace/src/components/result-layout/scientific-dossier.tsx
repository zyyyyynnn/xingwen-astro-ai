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
  readonly aside?: ReactNode;
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

/**
 * One scientific entry in a separator-divided dossier list. Accepted entries
 * stay typographic; only candidate review gets a light surface and rejected
 * entries mute. No per-entry card chrome.
 */
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
  aside = null,
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
    ? "bg-surface-muted/40 rounded-md"
    : isRejected
      ? "opacity-70"
      : "";

  const main = (
    <div className="flex min-w-0 flex-1 flex-col gap-2.5">
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
        <div className="flex flex-wrap items-center gap-2 pt-1">
          {evidenceActions}
        </div>
      ) : null}
    </div>
  );

  return (
    <article
      className={`xw-scientific-dossier border-b border-border/70 px-1 py-4 last:border-b-0 ${surfaceClass} ${className}`}
      data-status={status ?? undefined}
      data-testid={testId}
    >
      {aside ? (
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          {main}
          {aside}
        </div>
      ) : (
        main
      )}
    </article>
  );
}
