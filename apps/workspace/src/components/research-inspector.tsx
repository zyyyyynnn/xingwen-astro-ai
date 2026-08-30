import type { ReactNode } from "react";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
  Badge,
  Button,
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  Item,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
  Tabs,
  TabsList,
  TabsTrigger,
} from "@xingwen/ui";
import { FileSearch, Layers3, ListChecks, Target } from "@xingwen/ui/icons";

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
      <TabsList variant="line">
        <TabsTrigger value="overview">
          <Layers3 data-icon="inline-start" aria-hidden="true" />
          研究概览
        </TabsTrigger>
        <TabsTrigger value="results">
          <ListChecks data-icon="inline-start" aria-hidden="true" />
          研究结果
          {resultCount > 0 ? (
            <Badge variant="secondary">{resultCount}</Badge>
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
        <Accordion
          type="multiple"
          defaultValue={["goal", "plan"]}
          className="docked-workspace-content__stack"
        >
          <AccordionItem value="goal" className="docked-workspace-section">
            <AccordionTrigger>
              <span className="docked-workspace-section__title">
                <Target data-icon="inline-start" aria-hidden="true" />
                研究目标与范围
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <p className="docked-workspace-section__body">
                {contract?.researchGoal ??
                  draft?.intent ??
                  "研究助手生成协议后，研究边界会显示在这里。"}
              </p>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="plan" className="docked-workspace-section">
            <AccordionTrigger>
              <span className="docked-workspace-section__heading">
                <span className="docked-workspace-section__title">
                  <ListChecks data-icon="inline-start" aria-hidden="true" />
                  研究计划
                </span>
                <Badge variant="secondary">
                  {presentation.statusLabel} · {presentation.planItems.length}{" "}
                  项
                </Badge>
              </span>
            </AccordionTrigger>
            <AccordionContent>
              <ol className="docked-workspace-plan">
                {presentation.planItems.map((item) => (
                  <li key={item.id} data-status={item.status}>
                    <Item size="sm">
                      <ItemMedia>
                        <ResearchPlanStatusIcon status={item.status} />
                      </ItemMedia>
                      <ItemContent>
                        <ItemTitle>{item.label}</ItemTitle>
                        {item.detail ? (
                          <ItemDescription>{item.detail}</ItemDescription>
                        ) : null}
                      </ItemContent>
                    </Item>
                  </li>
                ))}
              </ol>
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      ) : null}

      {activeTab === "results"
        ? (resultPanel ?? (
            <Empty className="docked-workspace-empty">
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <FileSearch aria-hidden="true" />
                </EmptyMedia>
                <EmptyTitle>尚无研究结果</EmptyTitle>
                <EmptyDescription>
                  协议确认并开始运行后，研究产物会按依赖顺序显示在这里。
                </EmptyDescription>
              </EmptyHeader>
              <EmptyContent>
                <Button
                  type="button"
                  variant="secondary"
                  size="small"
                  onClick={() => setTab("overview")}
                >
                  返回研究概览
                </Button>
              </EmptyContent>
            </Empty>
          ))
        : null}
    </div>
  );
}

export function ResearchInspector(props: ResearchInspectorProps) {
  return <DockedWorkspacePanel {...props} />;
}
