import React from "react";
import {
  ScrollArea,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@xingwen/ui";
import { PanelRightClose, PanelRightOpen } from "@xingwen/ui/icons";

import { ChatInterfaceWrapper } from "./chat-interface-wrapper";
import { ConversationNameWithStatus } from "../conversation-name-with-status";
import {
  SIDEBAR_ICON_BUTTON_CLASS,
  SIDEBAR_RAIL_TRANSITION_CLASS,
} from "../../sidebar/sidebar-layout";
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

interface WorkspaceMainColumnStyle extends React.CSSProperties {
  readonly paddingInlineEnd: string;
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
    defaultLeftWidth: readToken("--workspace-panel-default-ratio"),
    minLeftWidth: readToken("--workspace-panel-min-ratio"),
    maxLeftWidth: readToken("--workspace-panel-max-ratio"),
    keyboardStep: readToken("--workspace-panel-keyboard-step"),
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

/** Current Workspace split-panel composition for the product-owned research detail rail. */
export function ConversationMain({ runtime }: ConversationMainProps) {
  const hasInspector = runtime.inspectorPanel !== null;
  const requestedInspector = runtime.inspectorRequest;
  const [storedInspector, setStoredInspector] = React.useState({
    available: hasInspector,
    visible: hasInspector,
  });
  const consumedRequestKey = React.useRef(requestedInspector?.key ?? null);
  const isNarrow = React.useSyncExternalStore(
    (callback) => {
      if (typeof window === "undefined" || !window.matchMedia) {
        return () => {};
      }
      const media = window.matchMedia("(max-width: 1024px)");
      media.addEventListener("change", callback);
      return () => media.removeEventListener("change", callback);
    },
    () => {
      if (typeof window === "undefined" || !window.matchMedia) return false;
      return window.matchMedia("(max-width: 1024px)").matches;
    },
    () => false,
  );

  const inspector =
    storedInspector.available === hasInspector
      ? storedInspector
      : { available: hasInspector, visible: hasInspector };
  const inspectorVisible = inspector.visible && hasInspector;
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
  const mainColumnStyle: WorkspaceMainColumnStyle = {
    paddingInlineEnd:
      !hasInspector || isNarrow
        ? "0px"
        : inspectorVisible
          ? `${rightWidth}%`
          : "0px",
  };

  React.useEffect(() => {
    if (
      !hasInspector ||
      requestedInspector === undefined ||
      consumedRequestKey.current === requestedInspector.key
    ) {
      return;
    }
    consumedRequestKey.current = requestedInspector.key;
    setStoredInspector({ available: true, visible: true });
  }, [hasInspector, requestedInspector]);

  const toggleInspector = () => {
    if (!hasInspector) return;
    setStoredInspector({ available: hasInspector, visible: !inspectorVisible });
  };

  const inspectorContent =
    runtime.inspectorDockedPanel ?? runtime.inspectorPanel;
  const inspectorHeading = runtime.inspectorDockedLabel ?? "研究概览";
  const inspectorToolbar = runtime.inspectorDockedToolbar;

  return (
    <section
      ref={containerRef}
      className="relative h-full min-h-0 overflow-hidden [container-type:inline-size]"
      aria-label="研究工作区"
      data-testid="conversation-main"
    >
      <div
        className={cn(
          "flex h-full min-h-0 min-w-0 flex-col bg-[var(--color-surface)] transition-[padding-inline-end] duration-[var(--workspace-motion-panel)] ease-[var(--workspace-ease-panel)] motion-reduce:transition-none",
          isDragging && "transition-none",
        )}
        style={mainColumnStyle}
        data-workspace-main-column=""
        data-testid="workspace-main-column"
      >
        <header
          className="flex h-[var(--workspace-header-block-size)] shrink-0 items-center gap-[var(--space-3)] border-b border-[var(--color-border)] px-[var(--workspace-header-inline-padding)] py-0"
          data-testid="workspace-topbar"
        >
          <div className="flex min-w-0 flex-1 items-center">
            <ConversationNameWithStatus runtime={runtime} />
          </div>
          {runtime.headerActions ? (
            <div className="workspace-topbar-actions">
              {runtime.headerActions}
            </div>
          ) : null}
        </header>
        <div
          className="relative flex min-h-0 flex-1 flex-col overflow-hidden"
          aria-labelledby="research-project-heading"
          data-testid="workspace-main-track"
        >
          <ChatInterfaceWrapper runtime={runtime} />
        </div>
      </div>

      {hasInspector && !isNarrow ? (
        <div
          className={cn(
            "absolute inset-y-0 z-[var(--workspace-layer-resize-handle)] transition-[right,opacity] duration-[var(--workspace-motion-panel)] ease-[var(--workspace-ease-panel)] motion-reduce:transition-none",
            !inspectorVisible && "pointer-events-none opacity-0",
            isDragging && "transition-none",
          )}
          style={{ right: inspectorVisible ? `${rightWidth}%` : "0px" }}
        >
          <ResizeHandle
            className="h-full"
            value={leftWidth}
            min={minLeftWidth}
            max={maxLeftWidth}
            onMouseDown={handleMouseDown}
            onKeyboardResize={handleKeyboardResize}
            isDragging={isDragging}
          />
        </div>
      ) : null}

      {hasInspector && !isNarrow ? (
        <aside
          id="research-inspector-panel"
          className={cn(
            "absolute inset-y-0 right-0 z-[var(--workspace-layer-header-toggle)] flex min-h-0 min-w-0 flex-col overflow-hidden border-l bg-[var(--color-surface-muted)]",
            SIDEBAR_RAIL_TRANSITION_CLASS,
            isDragging && "transition-none",
          )}
          style={{
            width: inspectorVisible ? `${rightWidth}%` : "0px",
            borderInlineStartColor: inspectorVisible
              ? "var(--color-border)"
              : "transparent",
          }}
          aria-label="右侧研究栏"
          data-testid="research-inspector-panel"
          data-collapsed={!inspectorVisible}
        >
          <div
            className="flex h-full min-h-0 flex-col"
            style={{ width: `${rightWidth}cqi` }}
          >
            <div className="flex h-[var(--workspace-header-block-size)] shrink-0 items-center gap-[var(--space-2)] border-b-0 px-[var(--space-5)] pe-[var(--workspace-header-control-reserve-inline)]">
              {inspectorToolbar ?? (
                <h2 className="min-w-0 truncate px-[var(--space-1)] text-[length:var(--font-size-ui-body)] font-medium text-[var(--color-ink-primary)]">
                  {inspectorHeading}
                </h2>
              )}
            </div>
            <ScrollArea className="min-h-0 flex-1">
              <div className="px-[var(--space-5)] pb-[var(--space-5)]">
                {inspectorContent}
              </div>
            </ScrollArea>
          </div>
        </aside>
      ) : null}

      {hasInspector && isNarrow ? (
        <Sheet
          open={inspectorVisible}
          onOpenChange={(open) =>
            setStoredInspector({ available: hasInspector, visible: open })
          }
        >
          <SheetContent
            side="right"
            className="flex w-[var(--workspace-result-sheet-narrow-inline-size)] max-w-full flex-col p-0"
          >
            <SheetHeader className="flex h-[var(--workspace-header-block-size)] shrink-0 items-center justify-between border-b border-[var(--color-border)] ps-[var(--space-5)] pe-[var(--workspace-header-control-reserve-inline)]">
              {inspectorToolbar ?? (
                <SheetTitle className="min-w-0 truncate text-[length:var(--font-size-ui-body)] font-medium text-[var(--color-ink-primary)]">
                  {inspectorHeading}
                </SheetTitle>
              )}
              <SheetDescription className="sr-only">
                研究概览与结果索引
              </SheetDescription>
            </SheetHeader>
            <ScrollArea className="min-h-0 flex-1">
              <div className="px-[var(--space-5)] pb-[var(--space-5)] pt-[var(--space-4)]">
                {inspectorContent}
              </div>
            </ScrollArea>
          </SheetContent>
        </Sheet>
      ) : null}

      {hasInspector ? (
        <button
          type="button"
          className={cn(
            SIDEBAR_ICON_BUTTON_CLASS,
            "absolute right-[var(--workspace-header-control-inset-inline)] top-[var(--workspace-header-control-inset-block)] z-[var(--workspace-layer-header-toggle)]",
          )}
          aria-label={inspectorVisible ? "关闭右侧研究栏" : "打开右侧研究栏"}
          aria-controls="research-inspector-panel"
          aria-expanded={inspectorVisible}
          onClick={toggleInspector}
        >
          {inspectorVisible ? (
            <PanelRightClose
              className="size-[var(--icon-size-md)]"
              aria-hidden="true"
            />
          ) : (
            <PanelRightOpen
              className="size-[var(--icon-size-md)]"
              aria-hidden="true"
            />
          )}
        </button>
      ) : null}
    </section>
  );
}

export default ConversationMain;
