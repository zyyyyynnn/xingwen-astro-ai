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

/** OpenHands disclosure mechanics with an explicit public-analysis boundary. */
export function CollapsibleThinking({
  content,
  isStreaming = false,
  label = "分析",
}: CollapsibleThinkingProps) {
  if (!content.trim()) return null;
  return (
    <Collapsible
      className="oh-narrative-node"
      data-testid="collapsible-thinking"
    >
      <CollapsibleTrigger asChild>
        <button type="button" className="oh-narrative-row oh-narrative-trigger">
          <ChevronDown
            className="oh-narrative-chevron xw-disclosure-chevron"
            aria-hidden="true"
          />
          <BrainCircuit className="oh-narrative-icon" aria-hidden="true" />
          <span className="oh-narrative-title flex items-center gap-[var(--oh-space-2)]">
            <span className="truncate">{label}</span>
            {isStreaming ? (
              <span className="shrink-0 text-xs text-[var(--oh-muted)]">
                进行中
              </span>
            ) : null}
          </span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="oh-narrative-content">
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

/** Retained as the upstream disclosure seam for public rationale consumers. */
export function NarrativeDisclosure({
  summary,
  children,
}: {
  readonly summary: string;
  readonly children: React.ReactNode;
}) {
  return (
    <Collapsible className="oh-narrative-node">
      <CollapsibleTrigger asChild>
        <button type="button" className="oh-narrative-row oh-narrative-trigger">
          <ChevronDown
            className="oh-narrative-chevron xw-disclosure-chevron"
            aria-hidden="true"
          />
          <BrainCircuit className="oh-narrative-icon" aria-hidden="true" />
          <span className="oh-narrative-title truncate">{summary}</span>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="oh-narrative-content">
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
