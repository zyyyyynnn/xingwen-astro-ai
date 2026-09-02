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
    ? "xw-scientific-dossier--candidate"
    : isRejected
      ? "xw-scientific-dossier--rejected"
      : "";

  const main = (
    <div className="xw-scientific-dossier__main">
      <header className="xw-scientific-dossier__header">
        <div className="xw-scientific-dossier__meta-row">
          <div className="xw-scientific-dossier__meta-group">
            {displayStatusLabel ? (
              <Badge variant={statusBadgeVariant(status)}>
                {displayStatusLabel}
              </Badge>
            ) : null}
            {category ? (
              <span className="xw-scientific-dossier__category">
                {category}
              </span>
            ) : null}
          </div>
          {actions ? (
            <div className="xw-scientific-dossier__actions">{actions}</div>
          ) : null}
        </div>

        <h4 className="xw-scientific-dossier__title">{title}</h4>

        {statement && statement !== title ? (
          <p className="xw-scientific-dossier__statement">{statement}</p>
        ) : null}
      </header>

      {facts.length > 0 ? <ScientificFactGrid facts={facts} /> : null}

      {children}

      {evidenceActions ? (
        <div className="xw-scientific-dossier__evidence-actions">
          {evidenceActions}
        </div>
      ) : null}
    </div>
  );

  return (
    <article
      className={`xw-scientific-dossier ${surfaceClass} ${className}`}
      data-status={status ?? undefined}
      data-testid={testId}
    >
      {aside ? (
        <div className="xw-scientific-dossier__with-aside lg:flex-row lg:items-start">
          {main}
          {aside}
        </div>
      ) : (
        main
      )}
    </article>
  );
}
