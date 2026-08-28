import type { ReactNode } from "react";
import {
  Badge,
  Button,
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@xingwen/ui";
import {
  ChevronDown,
  FileSearch,
  Layers3,
  ListChecks,
  Target,
} from "@xingwen/ui/icons";

import type {
  ResearchContractDraftViewModel,
  ResearchContractViewModel,
} from "@xingwen/research-adapter";
import type { ResearchPresentation } from "../presentation/research-presentation";
import { ResearchPlanStatusIcon } from "./research-plan";

export type ResearchInspectorTab = "overview" | "results";

export interface ResearchInspectorProps {
  readonly activeTab?: ResearchInspectorTab;
  readonly onTabChange?: (tab: ResearchInspectorTab) => void;
  readonly draft: ResearchContractDraftViewModel | null;
  readonly contract: ResearchContractViewModel | null;
  readonly presentation: ResearchPresentation;
  readonly resultPanel?: ReactNode;
}

export interface ResearchInspectorTabsProps {
  readonly activeTab: ResearchInspectorTab;
  readonly onTabChange: (tab: ResearchInspectorTab) => void;
  readonly resultCount?: number;
}

/**
 * The rail header owns navigation. The content below it only renders the
 * selected workspace surface; protocol editing intentionally lives in the
 * review dialog rather than becoming a second inline editor.
 */
export function ResearchInspectorTabs({
  activeTab,
  onTabChange,
  resultCount = 0,
}: ResearchInspectorTabsProps) {
  return (
    <Tabs
      value={activeTab}
      onValueChange={(val) => onTabChange(val as ResearchInspectorTab)}
      className="research-inspector-tabs min-w-0 flex-1"
      data-testid="research-inspector-tabs"
    >
      <TabsList className="h-8 justify-start gap-1 border-0 bg-transparent p-0">
        <TabsTrigger
          value="overview"
          className="h-7 gap-1.5 rounded-[var(--radius-md)] px-2.5 text-xs font-medium text-[var(--color-ink-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink-primary)] data-[state=active]:bg-[var(--color-surface-hover)] data-[state=active]:text-[var(--color-ink-primary)] data-[state=active]:shadow-none"
        >
          <Layers3 className="size-3.5" aria-hidden="true" />
          研究概览
        </TabsTrigger>
        <TabsTrigger
          value="results"
          className="h-7 gap-1.5 rounded-[var(--radius-md)] px-2.5 text-xs font-medium text-[var(--color-ink-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink-primary)] data-[state=active]:bg-[var(--color-surface-hover)] data-[state=active]:text-[var(--color-ink-primary)] data-[state=active]:shadow-none"
        >
          <ListChecks className="size-3.5" aria-hidden="true" />
          研究结果
          {resultCount > 0 ? (
            <Badge
              variant="secondary"
              className="ui-text-label h-4 min-w-4 px-1"
            >
              {resultCount}
            </Badge>
          ) : null}
        </TabsTrigger>
      </TabsList>
    </Tabs>
  );
}

export function DockedWorkspacePanel({
  activeTab: controlledTab,
  onTabChange,
  draft,
  contract,
  presentation,
  resultPanel,
}: ResearchInspectorProps) {
  const activeTab = controlledTab ?? "overview";
  const setTab = onTabChange ?? (() => undefined);

  return (
    <div
      className="docked-workspace-content"
      data-testid="docked-workspace-panel"
      data-active-tab={activeTab}
    >
      {activeTab === "overview" ? (
        <div className="docked-workspace-content__stack flex flex-col gap-5 py-3">
          <Collapsible
            defaultOpen
            className="docked-workspace-section group/goal"
          >
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                className="flex h-auto w-full items-center justify-between gap-2 p-0 text-left font-normal hover:bg-transparent"
                aria-label="折叠或展开研究目标与范围"
              >
                <h3 className="docked-workspace-section__title">
                  <Target
                    className="size-4 text-[var(--color-ink-secondary)]"
                    aria-hidden="true"
                  />
                  研究目标与范围
                </h3>
                <ChevronDown
                  className="xw-disclosure-chevron size-3.5 text-[var(--color-ink-secondary)] group-data-[state=open]/goal:rotate-180"
                  aria-hidden="true"
                />
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <p className="docked-workspace-section__body">
                {contract?.researchGoal ??
                  draft?.intent ??
                  "研究助手生成协议后，研究边界会显示在这里。"}
              </p>
            </CollapsibleContent>
          </Collapsible>

          <Collapsible
            defaultOpen
            className="docked-workspace-section group/plan"
          >
            <CollapsibleTrigger asChild>
              <Button
                type="button"
                variant="ghost"
                className="flex h-auto w-full items-center justify-between gap-2 p-0 text-left font-normal hover:bg-transparent"
                aria-label="折叠或展开研究计划"
              >
                <div className="flex items-center gap-2">
                  <h3 className="docked-workspace-section__title">
                    <ListChecks
                      className="size-4 text-[var(--color-ink-secondary)]"
                      aria-hidden="true"
                    />
                    研究计划
                  </h3>
                  <span className="docked-workspace-section__meta">
                    {presentation.statusLabel}
                  </span>
                </div>
                <div className="flex items-center gap-1.5">
                  {presentation.planItems.length > 0 ? (
                    <span className="docked-workspace-section__meta">
                      {presentation.planItems.length} 项
                    </span>
                  ) : null}
                  <ChevronDown
                    className="xw-disclosure-chevron size-3.5 text-[var(--color-ink-secondary)] group-data-[state=open]/plan:rotate-180"
                    aria-hidden="true"
                  />
                </div>
              </Button>
            </CollapsibleTrigger>
            <CollapsibleContent>
              <ol className="docked-workspace-plan">
                {presentation.planItems.map((item) => (
                  <li key={item.id} data-status={item.status}>
                    <ResearchPlanStatusIcon status={item.status} />
                    <span>{item.label}</span>
                  </li>
                ))}
              </ol>
            </CollapsibleContent>
          </Collapsible>
        </div>
      ) : null}

      {activeTab === "results"
        ? (resultPanel ?? (
            <div className="docked-workspace-empty">
              <FileSearch aria-hidden="true" />
              <p>研究完成后，产物会显示在这里。</p>
              <Button
                type="button"
                variant="ghost"
                size="small"
                onClick={() => setTab("overview")}
              >
                返回研究概览
              </Button>
            </div>
          ))
        : null}
    </div>
  );
}

export function ResearchInspector(props: ResearchInspectorProps) {
  return <DockedWorkspacePanel {...props} />;
}
