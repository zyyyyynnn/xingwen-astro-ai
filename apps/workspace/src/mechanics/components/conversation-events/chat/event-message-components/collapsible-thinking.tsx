import React from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@xingwen/ui";
import { BrainCircuit, ChevronDown } from "@xingwen/ui/icons";

interface CollapsibleThinkingProps {
  /** Server-validated public analysis, never provider-private chain of thought. */
  readonly content: string;
  readonly isStreaming?: boolean;
  readonly label?: string;
}

/** Public-analysis disclosure mechanics. */
export function CollapsibleThinking({
  content,
  isStreaming = false,
  label = "分析",
}: CollapsibleThinkingProps) {
  if (!content.trim()) return null;
  return (
    <Collapsible
      className="workspace-narrative-node"
      data-testid="collapsible-thinking"
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="workspace-narrative-row workspace-narrative-trigger"
        >
          <ChevronDown
            className="workspace-narrative-chevron xw-disclosure-chevron"
            aria-hidden="true"
          />
          <BrainCircuit
            className="workspace-narrative-icon"
            aria-hidden="true"
          />
          <span className="workspace-narrative-title flex items-center gap-[var(--space-2)]">
            <span className="truncate">{label}</span>
            {isStreaming ? (
              <span className="shrink-0 text-xs text-[var(--color-ink-secondary)]">
                进行中
              </span>
            ) : null}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="workspace-narrative-content">
        <div
          role="region"
          data-testid="collapsible-thinking-content"
          className="whitespace-pre-wrap"
        >
          {content}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

/** Disclosure seam for public rationale consumers. */
export function NarrativeDisclosure({
  summary,
  children,
}: {
  readonly summary: string;
  readonly children: React.ReactNode;
}) {
  return (
    <Collapsible className="workspace-narrative-node">
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="workspace-narrative-row workspace-narrative-trigger"
        >
          <ChevronDown
            className="workspace-narrative-chevron xw-disclosure-chevron"
            aria-hidden="true"
          />
          <BrainCircuit
            className="workspace-narrative-icon"
            aria-hidden="true"
          />
          <span className="workspace-narrative-title truncate">{summary}</span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="workspace-narrative-content">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
