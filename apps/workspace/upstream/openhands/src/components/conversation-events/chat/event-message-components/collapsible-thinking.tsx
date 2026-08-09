import React from "react";
import { ChevronDown, FileSearch } from "lucide-react";

interface CollapsibleRationaleProps {
  readonly summary: string;
  readonly children: React.ReactNode;
}

/** Disclosure for public, auditable rationale only. */
export function CollapsibleRationale({
  summary,
  children,
}: CollapsibleRationaleProps) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <section className="border-l border-[var(--oh-border-strong)] pl-[var(--oh-space-3)] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]">
      <button
        type="button"
        onClick={() => setExpanded((current) => !current)}
        aria-expanded={expanded}
        className="flex w-full items-center gap-[var(--oh-space-2)] border-0 bg-transparent px-0 py-[var(--oh-space-1)] text-left text-[var(--oh-muted)] hover:text-[var(--oh-text)]"
      >
        <ChevronDown
          className={`size-[var(--oh-icon-size-md)] shrink-0 transition-transform motion-reduce:transition-none ${expanded ? "rotate-180" : ""}`}
          aria-hidden="true"
        />
        <FileSearch
          className="size-[var(--oh-icon-size-md)] shrink-0"
          aria-hidden="true"
        />
        <span>{summary}</span>
      </button>
      {expanded ? (
        <div className="pb-[var(--oh-space-2)] pl-[var(--oh-space-6)] pt-[var(--oh-space-1)] text-[var(--oh-text)]">
          {children}
        </div>
      ) : null}
    </section>
  );
}
