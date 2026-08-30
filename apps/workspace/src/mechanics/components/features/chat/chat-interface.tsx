import React from "react";
import {
  Item,
  ItemContent,
  ItemDescription,
  ItemMedia,
  ItemTitle,
} from "@xingwen/ui";
import {
  BrainCircuit,
  Database,
  FileSearch,
  type LucideIcon,
} from "@xingwen/ui/icons";

import type { ResearchWorkspaceRuntime } from "../../../root";
import { useScrollToBottom } from "../../../hooks/use-scroll-to-bottom";
import { ScrollToBottomButton } from "../../shared/buttons/scroll-to-bottom-button";
import { InteractiveChatBox } from "./interactive-chat-box";

interface ChatInterfaceProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

const RESEARCH_STARTERS: ReadonlyArray<{
  readonly title: string;
  readonly description: string;
  readonly prompt: string;
  readonly icon: LucideIcon;
}> = [
  {
    title: "构建证据综述",
    description: "汇总文献、论点关系与可追溯证据",
    prompt:
      "围绕我的研究问题构建一份可追溯证据的文献综述，并标出关键争议与证据缺口。",
    icon: FileSearch,
  },
  {
    title: "分析观测数据",
    description: "检查数据质量、信号特征与异常来源",
    prompt:
      "分析我提供的观测数据，先核对数据质量与来源，再识别显著信号和可能的异常。",
    icon: Database,
  },
  {
    title: "比较科研模型",
    description: "建立基线、评估差异并解释限制",
    prompt:
      "为当前科研问题设计模型比较方案，给出基线、评估指标、证据依据与主要限制。",
    icon: BrainCircuit,
  },
];

export function ChatInterface({ runtime }: ChatInterfaceProps) {
  const composer = runtime.composer;
  const hasStartedConversation = composer?.hasStartedConversation ?? false;
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const endRef = React.useRef<HTMLDivElement>(null);
  const {
    autoScroll,
    hitBottom,
    onChatBodyScroll,
    pendingNewCount,
    scrollDomToBottom,
  } = useScrollToBottom(scrollRef, runtime.threadItemCount);
  const inspectorInsetStyle = {
    paddingInlineEnd: "var(--workspace-inspector-reserved-inline-size, 0px)",
  };

  React.useLayoutEffect(() => {
    if (autoScroll) {
      endRef.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [autoScroll, runtime.threadPanel, composer?.submitting]);

  const handleSubmit = async (message: string) => {
    scrollDomToBottom();
    await composer?.onSubmit(message);
  };

  return (
    <div
      className={`relative flex h-full min-h-0 flex-col ${hasStartedConversation ? "" : "justify-center"}`}
      data-testid="chat-interface"
    >
      <div
        ref={scrollRef}
        data-testid="chat-scroll-container"
        className={
          hasStartedConversation
            ? "custom-scrollbar-always min-h-0 grow overflow-x-hidden overflow-y-auto transition-[padding-inline-end] duration-[var(--workspace-motion-panel)] ease-[var(--workspace-ease-panel)] motion-reduce:transition-none"
            : "shrink-0 overflow-visible transition-[padding-inline-end] duration-[var(--workspace-motion-panel)] ease-[var(--workspace-ease-panel)] motion-reduce:transition-none"
        }
        style={inspectorInsetStyle}
        aria-live="polite"
        aria-busy={composer?.submitting ?? false}
        onScroll={(event) => onChatBodyScroll(event.currentTarget)}
      >
        <div
          className={`flex flex-col px-4 md:px-8 ${hasStartedConversation ? "min-h-full pb-8 pt-4" : ""}`}
        >
          {runtime.threadPanel}
          <div ref={endRef} aria-hidden="true" />
        </div>
      </div>
      {composer ? (
        <div
          className="relative shrink-0 transition-[padding-inline-end] duration-[var(--workspace-motion-panel)] ease-[var(--workspace-ease-panel)] motion-reduce:transition-none"
          data-testid="chat-composer-track"
          style={inspectorInsetStyle}
        >
          <div
            className={`relative px-4 md:px-8 ${hasStartedConversation ? "pb-4" : ""}`}
            data-testid="chat-composer-gutter"
          >
            {!hasStartedConversation ? (
              <div className="mx-auto mb-[var(--space-6)] flex w-full max-w-[var(--workspace-content-max-inline-size)] flex-col gap-[var(--space-6)]">
                <div className="mx-auto flex max-w-[var(--workspace-result-reading-max-inline-size)] flex-col items-center text-center">
                  <h1
                    className="workspace-font-serif text-3xl font-medium tracking-tight text-[var(--color-ink-primary)]"
                    role="heading"
                    aria-level={1}
                  >
                    开始你的研究
                  </h1>
                  <p className="mt-[var(--space-3)] text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)] text-[var(--color-ink-secondary)]">
                    从问题或数据出发，把文献、分析、证据和版本化成果组织在同一条研究链路中。
                  </p>
                </div>

                <section aria-labelledby="research-starters-heading">
                  <h2
                    id="research-starters-heading"
                    className="mb-[var(--space-2)] text-[length:var(--font-size-ui-label)] font-medium text-[var(--color-ink-secondary)]"
                  >
                    选择研究起点，或直接描述你的目标
                  </h2>
                  <div className="workspace-research-starters">
                    {RESEARCH_STARTERS.map((starter) => {
                      const Icon = starter.icon;
                      return (
                        <Item
                          key={starter.title}
                          asChild
                          variant="default"
                          size="sm"
                          className="workspace-research-starter min-h-[var(--workspace-entry-starter-block-size)] cursor-pointer items-start text-left hover:bg-[var(--color-surface-hover)]"
                        >
                          <button
                            type="button"
                            onClick={() =>
                              composer?.onValueChange(starter.prompt)
                            }
                          >
                            <ItemMedia className="mt-[var(--space-1)] text-[var(--color-brand)]">
                              <Icon
                                className="size-[var(--icon-size-md)]"
                                aria-hidden="true"
                              />
                            </ItemMedia>
                            <ItemContent>
                              <ItemTitle>{starter.title}</ItemTitle>
                              <ItemDescription>
                                {starter.description}
                              </ItemDescription>
                            </ItemContent>
                          </button>
                        </Item>
                      );
                    })}
                  </div>
                </section>
              </div>
            ) : null}
            <div className="relative mx-auto flex w-full max-w-[var(--workspace-content-max-inline-size)] flex-col gap-[var(--space-2)]">
              {hasStartedConversation && !hitBottom ? (
                <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2">
                  <ScrollToBottomButton
                    onClick={scrollDomToBottom}
                    newCount={pendingNewCount}
                  />
                </div>
              ) : null}
              {composer.beforeInput}
              <div className="relative">
                <InteractiveChatBox
                  value={composer.value}
                  disabled={false}
                  submitting={composer.submitting}
                  placeholder={composer.placeholder}
                  leadingActions={composer.leadingActions}
                  hasStartedConversation={composer.hasStartedConversation}
                  onFilesSelected={composer.onFilesSelected}
                  onDragOver={composer.onDragOver}
                  onDragLeave={composer.onDragLeave}
                  onDropFiles={composer.onDropFiles}
                  dragActive={composer.dragActive}
                  onValueChange={composer.onValueChange}
                  onSubmit={handleSubmit}
                />
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
