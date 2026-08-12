import React from "react";
import { ScrollArea, buttonClassName } from "@xingwen/ui";
import { Layers3, PanelRightClose, PanelRightOpen } from "@xingwen/ui/icons";

import { ChatInterfaceWrapper } from "./chat-interface-wrapper";
import { ConversationNameWithStatus } from "../conversation-name-with-status";
import { ResizeHandle } from "../../../ui/resize-handle";
import { useResizablePanels } from "../../../../hooks/use-resizable-panels";
import type { ResearchWorkspaceRuntime } from "../../../../root";
import { cn } from "../../../../utils/utils";

interface WorkspacePanelLayout {
  readonly defaultLeftWidth: number;
  readonly minLeftWidth: number;
  readonly maxLeftWidth: number;
  readonly keyboardStep: number;
}

function readWorkspacePanelLayout(): WorkspacePanelLayout {
  if (typeof document === "undefined") {
    throw new Error(
      "Workspace panel geometry requires a browser CSS token boundary.",
    );
  }

  const styles = window.getComputedStyle(document.documentElement);
  const readToken = (name: string) => {
    const value = Number.parseFloat(styles.getPropertyValue(name));
    if (!Number.isFinite(value)) {
      throw new Error(`Workspace panel token ${name} is missing or invalid.`);
    }
    return value;
  };

  const layout = {
    defaultLeftWidth: readToken("--oh-panel-default-ratio"),
    minLeftWidth: readToken("--oh-panel-min-ratio"),
    maxLeftWidth: readToken("--oh-panel-max-ratio"),
    keyboardStep: readToken("--oh-panel-keyboard-step"),
  };
  if (
    !(
      layout.minLeftWidth < layout.defaultLeftWidth &&
      layout.defaultLeftWidth < layout.maxLeftWidth
    ) ||
    layout.keyboardStep <= 0
  ) {
    throw new Error(
      "Workspace panel tokens must satisfy min < default < max and keyboard step > 0.",
    );
  }
  return layout;
}

interface ConversationMainProps {
  readonly runtime: ResearchWorkspaceRuntime;
}

/**
 * OpenHands ConversationMain with the coding/mobile content removed.
 * The split-panel, resize, panel visibility and header composition remain in
 * the upstream component boundary; Xingwen only supplies neutral surfaces and
 * the thin runtime seam.
 */
export function ConversationMain({ runtime }: ConversationMainProps) {
  return <ConversationMainSurface runtime={runtime} />;
}

function ConversationMainSurface({ runtime }: ConversationMainProps) {
  const hasInspector = runtime.inspectorPanel !== null;
  const [storedInspector, setStoredInspector] = React.useState<{
    readonly available: boolean;
    readonly mode: "floating" | "docked";
    readonly visible: boolean;
  }>({
    available: hasInspector,
    mode: "floating",
    visible: hasInspector,
  });
  const inspector =
    storedInspector.available === hasInspector
      ? storedInspector
      : {
          available: hasInspector,
          mode: "floating" as const,
          visible: hasInspector,
        };
  const inspectorMode = inspector.mode;
  const inspectorVisible = inspector.visible;
  const isFloatingLayout = inspectorMode === "floating";
  const isDockedLayout = inspectorMode === "docked";
  const isFloating = inspectorVisible && isFloatingLayout;
  const isDocked = inspectorVisible && isDockedLayout;
  const panelLayout = readWorkspacePanelLayout();
  const {
    leftWidth,
    rightWidth,
    minLeftWidth,
    maxLeftWidth,
    isDragging,
    containerRef,
    handleMouseDown,
    handleKeyboardResize,
  } = useResizablePanels({
    ...panelLayout,
    storageKey: "xingwen-agent-panel-width",
  });

  const safeAreaStyle = {
    "--oh-inspector-safe-area": isFloating ? "min(21rem, 36cqw)" : "0px",
  } as React.CSSProperties;

  const toggleInspector = (nextMode: "floating" | "docked") => {
    if (inspectorMode === nextMode) {
      setStoredInspector({
        available: hasInspector,
        mode: nextMode,
        visible: !inspectorVisible,
      });
      return;
    }
    setStoredInspector({
      available: hasInspector,
      mode: nextMode,
      visible: false,
    });
    requestAnimationFrame(() =>
      setStoredInspector({
        available: hasInspector,
        mode: nextMode,
        visible: true,
      }),
    );
  };

  const inspectorBody = (
    <ScrollArea className="min-h-0 flex-1">
      <div className="px-[var(--oh-space-5)] pb-[var(--oh-space-5)]">
        {runtime.inspectorPanel}
      </div>
    </ScrollArea>
  );

  return (
    <section
      className="relative h-full min-h-0"
      aria-label="研究工作区"
      data-testid="conversation-main"
    >
      <div
        ref={containerRef}
        className="relative flex h-full min-h-0 overflow-hidden [container-type:inline-size]"
      >
        <div
          className="flex min-w-0 flex-1 flex-col overflow-hidden"
          data-workspace-main-column=""
        >
          <header className="flex h-[var(--oh-header-block-size)] shrink-0 items-center gap-[var(--oh-space-3)] border-b border-[var(--oh-border)] px-[var(--oh-header-inline-padding)] py-0">
            <div className="flex min-w-0 flex-1 items-center">
              <ConversationNameWithStatus runtime={runtime} />
            </div>
            {hasInspector ? (
              <div className="flex shrink-0 items-center gap-[var(--oh-space-1)]">
                <button
                  type="button"
                  className={buttonClassName({
                    variant: "ghost",
                    size: "icon",
                    className: isFloating
                      ? "bg-[var(--oh-surface-raised)] text-[var(--oh-text)]"
                      : undefined,
                  })}
                  aria-label={isFloating ? "收起悬浮概览" : "展示悬浮概览"}
                  aria-controls="research-inspector-panel"
                  aria-pressed={isFloating}
                  onClick={() => toggleInspector("floating")}
                >
                  <Layers3
                    className="size-[var(--oh-icon-size-md)]"
                    aria-hidden="true"
                  />
                </button>
                <button
                  type="button"
                  className={buttonClassName({
                    variant: "ghost",
                    size: "icon",
                    className: isDocked
                      ? "bg-[var(--oh-surface-raised)] text-[var(--oh-text)]"
                      : undefined,
                  })}
                  aria-label={isDocked ? "收起右侧栏" : "展开右侧栏"}
                  aria-controls="research-inspector-panel"
                  aria-pressed={isDocked}
                  onClick={() => toggleInspector("docked")}
                >
                  {isDocked ? (
                    <PanelRightClose
                      className="size-[var(--oh-icon-size-md)]"
                      aria-hidden="true"
                    />
                  ) : (
                    <PanelRightOpen
                      className="size-[var(--oh-icon-size-md)]"
                      aria-hidden="true"
                    />
                  )}
                </button>
              </div>
            ) : null}
          </header>

          <div className="relative flex min-h-0 flex-1 overflow-hidden [container-type:inline-size]">
            <div
              className="flex min-w-0 flex-1 flex-col overflow-hidden bg-[var(--oh-surface)]"
              aria-labelledby="research-project-heading"
              style={safeAreaStyle}
            >
              <ChatInterfaceWrapper runtime={runtime} />
            </div>

            {hasInspector && isFloatingLayout ? (
              <aside
                id="research-inspector-panel"
                className={cn(
                  "absolute bottom-[var(--oh-space-4)] right-[var(--oh-space-4)] top-[var(--oh-space-3)] z-[var(--oh-layer-header-toggle)] w-[min(18rem,30cqw)] origin-top-right overflow-hidden transition-[opacity,transform,visibility] duration-[var(--oh-motion-navigation)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none",
                  inspectorVisible
                    ? "visible translate-x-0 scale-100 opacity-100"
                    : "invisible translate-x-[var(--oh-space-2)] scale-[0.98] opacity-0",
                )}
                aria-label="悬浮研究概览"
                aria-hidden={!inspectorVisible}
                inert={!inspectorVisible}
                data-inspector-mode="floating"
              >
                <div className="research-inspector-floating flex max-h-full min-h-0 min-w-0 flex-col rounded-[var(--oh-radius-lg)] bg-[var(--oh-surface)] shadow-[var(--oh-shadow-float)]">
                  <div className="flex shrink-0 items-center px-[var(--oh-space-5)] pb-[var(--oh-space-2)] pt-[var(--oh-space-4)]">
                    <h2 className="text-[length:var(--oh-font-size-body)] font-medium text-[var(--oh-text)]">
                      研究概览
                    </h2>
                  </div>
                  {inspectorBody}
                </div>
              </aside>
            ) : null}
          </div>
        </div>

        {isDocked ? (
          <ResizeHandle
            value={leftWidth}
            min={minLeftWidth}
            max={maxLeftWidth}
            onMouseDown={handleMouseDown}
            onKeyboardResize={handleKeyboardResize}
            isDragging={isDragging}
          />
        ) : null}

        {hasInspector && isDockedLayout ? (
          <aside
            id="research-inspector-panel"
            className={cn(
              "relative h-full min-w-0 shrink-0 overflow-hidden bg-[var(--oh-surface-muted)] transition-[width] duration-[var(--oh-motion-panel)] ease-[var(--oh-ease-panel)] motion-reduce:transition-none",
              isDragging && "transition-none",
            )}
            aria-label="右侧研究栏"
            aria-hidden={!inspectorVisible}
            inert={!inspectorVisible}
            data-inspector-mode="docked"
            style={{
              width: inspectorVisible ? `${rightWidth}%` : "0%",
            }}
          >
            <div
              className="research-inspector-docked absolute inset-y-0 right-0 flex min-h-0 min-w-0 flex-col border-l border-[var(--oh-border)] bg-[var(--oh-surface-muted)]"
              style={{ width: `${rightWidth}cqw` }}
            >
              <header className="flex h-[var(--oh-header-block-size)] shrink-0 items-center border-b border-[var(--oh-border)] px-[var(--oh-space-5)]">
                <h2 className="text-[length:var(--oh-font-size-body)] font-medium text-[var(--oh-text)]">
                  研究概览
                </h2>
              </header>
              {inspectorBody}
            </div>
          </aside>
        ) : null}
      </div>
    </section>
  );
}

export default ConversationMain;
