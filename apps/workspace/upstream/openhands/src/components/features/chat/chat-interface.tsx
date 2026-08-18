import React from "react";

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
  const {
    autoScroll,
    hitBottom,
    onChatBodyScroll,
    pendingNewCount,
    scrollDomToBottom,
  } = useScrollToBottom(scrollRef, runtime.threadItemCount);
  const inspectorInsetStyle = {
    paddingInlineEnd: "var(--oh-workspace-inspector-reserved-inline-size, 0px)",
  };

  React.useLayoutEffect(() => {
    if (autoScroll) {
      endRef.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [autoScroll, runtime.threadPanel, composer?.submitting]);

  const handleSubmit = async (message: string) => {
    // Sending the user's own message always resumes bottom-follow first.
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
            ? "custom-scrollbar-always min-h-0 grow overflow-x-hidden overflow-y-auto transition-[padding-inline-end] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none"
            : "shrink-0 overflow-visible transition-[padding-inline-end] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none"
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
          className="relative shrink-0 transition-[padding-inline-end] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none"
          data-testid="chat-composer-track"
          style={inspectorInsetStyle}
        >
          <div
            className={`relative px-4 md:px-8 ${hasStartedConversation ? "pb-4" : ""}`}
            data-testid="chat-composer-gutter"
          >
            {!hasStartedConversation ? (
              <div className="mx-auto mb-6 flex w-full max-w-[var(--oh-content-max-inline-size)] flex-col items-center text-center">
                <h1
                  className="oh-font-serif text-2xl font-medium tracking-tight text-[var(--oh-text)]"
                  role="heading"
                  aria-level={1}
                >
                  开始你的研究
                </h1>
              </div>
            ) : null}
            <div className="relative mx-auto flex w-full max-w-[var(--oh-content-max-inline-size)] flex-col gap-[var(--oh-space-2)]">
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
