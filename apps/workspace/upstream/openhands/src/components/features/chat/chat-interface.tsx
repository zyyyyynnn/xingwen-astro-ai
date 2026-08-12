import React from "react";
import { Button } from "@xingwen/ui";
import { FileSearch } from "@xingwen/ui/icons";

import type { ResearchWorkspaceRuntime } from "../../../root";
import { useScrollToBottom } from "../../../hooks/use-scroll-to-bottom";
import { ScrollToBottomButton } from "../../shared/buttons/scroll-to-bottom-button";
import { InteractiveChatBox } from "./interactive-chat-box";

interface ChatInterfaceProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

export function ChatInterface({ runtime }: ChatInterfaceProps) {
  const composer = runtime.composer;
  const hasStartedConversation = composer?.hasStartedConversation ?? false;
  const scrollRef = React.useRef<HTMLDivElement>(null);
  const endRef = React.useRef<HTMLDivElement>(null);
  const { autoScroll, hitBottom, onChatBodyScroll, scrollDomToBottom } =
    useScrollToBottom(scrollRef);

  React.useLayoutEffect(() => {
    if (autoScroll) {
      endRef.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [autoScroll, runtime.threadPanel, composer?.submitting]);

  if (runtime.activation) {
    return (
      <div className="flex min-h-0 flex-1 flex-col bg-[var(--oh-canvas)]">
        <div className="flex min-h-full items-center justify-center px-[var(--oh-space-8)] py-[var(--oh-space-8)] text-center">
          <section
            className="max-w-md"
            aria-labelledby="workspace-activation-title"
          >
            <FileSearch
              className="mx-auto size-7 text-[var(--oh-text-dim)]"
              aria-hidden="true"
            />
            <h2
              id="workspace-activation-title"
              className="oh-font-serif mt-[var(--oh-space-4)] text-[length:var(--oh-font-size-heading)] leading-[var(--oh-line-height-heading)] font-medium text-[var(--oh-text)]"
            >
              {runtime.activation.title}
            </h2>
            <p className="mx-auto mt-[var(--oh-space-2)] max-w-[60ch] text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-muted)]">
              {runtime.activation.description}
            </p>
            <Button
              className="mt-[var(--oh-space-5)]"
              onClick={runtime.activation.onAction}
            >
              {runtime.activation.actionLabel}
            </Button>
          </section>
        </div>
      </div>
    );
  }

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
            ? "custom-scrollbar-always min-h-0 grow overflow-x-hidden overflow-y-auto"
            : "shrink-0 overflow-visible"
        }
        aria-live="polite"
        aria-busy={composer?.submitting ?? false}
        onScroll={(event) => onChatBodyScroll(event.currentTarget)}
      >
        <div
          className={`flex flex-col px-4 transition-[padding-right] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none md:px-8 ${hasStartedConversation ? "min-h-full pb-8 pt-4" : ""}`}
          style={{ paddingRight: "var(--oh-inspector-safe-area, 2rem)" }}
        >
          {runtime.threadPanel}
          <div ref={endRef} aria-hidden="true" />
        </div>
      </div>
      {composer ? (
        <div
          className={`relative shrink-0 px-4 transition-[padding-right] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none md:px-8 ${hasStartedConversation ? "pb-4" : ""}`}
          style={{ paddingRight: "var(--oh-inspector-safe-area, 2rem)" }}
        >
          <div className="relative mx-auto flex w-full max-w-[var(--oh-content-max-inline-size)] flex-col gap-[var(--oh-space-2)]">
            {hasStartedConversation && !hitBottom ? (
              <div className="absolute bottom-full left-1/2 mb-2 -translate-x-1/2">
                <ScrollToBottomButton onClick={scrollDomToBottom} />
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
                onValueChange={composer.onValueChange}
                onSubmit={composer.onSubmit}
              />
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
