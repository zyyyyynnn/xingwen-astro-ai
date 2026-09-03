import React from "react";
import { createPortal } from "react-dom";
import { buttonClassName } from "@xingwen/ui";
import { Search, X } from "@xingwen/ui/icons";

import { useCommandMenuStore } from "../../../stores/command-menu-store";
import { useSidebarStore } from "../../../stores/sidebar-store";
import { cn } from "../../../utils/utils";

import {
  COMMAND_MENU_GROUP_LABELS,
  COMMAND_MENU_GROUP_ORDER,
  type CommandMenuItemDefinition,
  createCommandMenuItems,
} from "./command-menu-items";

const SEARCH_INPUT_ID = "command-menu-search";
const LISTBOX_ID = "command-menu-results";

function optionId(item: CommandMenuItemDefinition) {
  return `command-menu-option-${item.id}`;
}

function matchesQuery(item: CommandMenuItemDefinition, query: string) {
  const terms = query.trim().toLocaleLowerCase().split(/\s+/).filter(Boolean);
  if (terms.length === 0) return true;
  const searchable =
    `${item.title} ${item.description} ${item.keywords}`.toLocaleLowerCase();
  return terms.every((term) => searchable.includes(term));
}

export function CommandMenu({
  projects,
  onOpenProject,
}: {
  readonly projects: readonly import("../../../root").ResearchNavigationItem[];
  readonly onOpenProject: (projectId: string) => void;
}) {
  const isOpen = useCommandMenuStore((state) => state.isOpen);
  const open = useCommandMenuStore((state) => state.open);
  const close = useCommandMenuStore((state) => state.close);
  const [query, setQuery] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement>(null);
  const optionRefs = React.useRef(new Map<string, HTMLElement>());
  const previousFocusRef = React.useRef<HTMLElement | null>(null);
  const wasOpenRef = React.useRef(false);

  React.useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        (event.metaKey || event.ctrlKey) &&
        event.key.toLocaleLowerCase() === "k"
      ) {
        event.preventDefault();
        open();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  React.useEffect(() => {
    if (isOpen) {
      const activeElement = document.activeElement;
      previousFocusRef.current =
        activeElement instanceof HTMLElement ? activeElement : null;
      const frame = requestAnimationFrame(() => inputRef.current?.focus());
      wasOpenRef.current = true;
      return () => cancelAnimationFrame(frame);
    }

    if (wasOpenRef.current) {
      previousFocusRef.current?.focus();
      previousFocusRef.current = null;
      wasOpenRef.current = false;
    }
    optionRefs.current.clear();
    return undefined;
  }, [isOpen]);

  const items = React.useMemo(
    () =>
      createCommandMenuItems({
        projects,
        onOpenProject,
        toggleSidebar: () => useSidebarStore.getState().toggleCollapsed(),
      }),
    [projects, onOpenProject],
  );
  const filteredItems = React.useMemo(
    () => items.filter((item) => matchesQuery(item, query)),
    [items, query],
  );

  const boundedActiveIndex =
    filteredItems.length === 0
      ? -1
      : Math.min(Math.max(activeIndex, 0), filteredItems.length - 1);

  React.useEffect(() => {
    const activeItem = filteredItems[boundedActiveIndex];
    const activeNode = activeItem
      ? optionRefs.current.get(activeItem.id)
      : undefined;
    activeNode?.scrollIntoView?.({ block: "nearest" });
  }, [boundedActiveIndex, filteredItems]);

  const dismiss = React.useCallback(() => {
    setQuery("");
    setActiveIndex(0);
    close();
  }, [close]);

  const runItem = (item: CommandMenuItemDefinition | undefined) => {
    if (!item) return;
    dismiss();
    item.perform();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((index) =>
        filteredItems.length === 0 ? index : (index + 1) % filteredItems.length,
      );
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) =>
        filteredItems.length === 0
          ? index
          : (index - 1 + filteredItems.length) % filteredItems.length,
      );
    } else if (event.key === "Enter") {
      event.preventDefault();
      runItem(filteredItems[boundedActiveIndex]);
    }
  };

  if (!isOpen || typeof document === "undefined") return null;

  const activeItem = filteredItems[boundedActiveIndex];

  return createPortal(
    <div
      className="fixed inset-0 z-[var(--workspace-layer-command-menu)] flex items-start justify-center bg-[var(--color-overlay)] px-[var(--space-6)] pt-[var(--workspace-command-menu-viewport-offset)]"
      data-testid="command-menu"
      role="dialog"
      aria-modal="true"
      aria-label="命令菜单"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          dismiss();
        } else if (event.key === "Tab") {
          event.preventDefault();
          inputRef.current?.focus();
        }
      }}
    >
      <button
        type="button"
        className="absolute inset-0 cursor-default border-0 bg-transparent"
        tabIndex={-1}
        aria-label="关闭命令菜单"
        onClick={dismiss}
      />
      <div className="relative flex max-h-[var(--workspace-command-menu-max-block-size)] w-full max-w-[var(--workspace-command-menu-max-inline-size)] flex-col overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface)] shadow-[var(--shadow-modal)]">
        <div className="group flex items-center gap-[var(--space-3)] border-b border-[var(--color-border)] px-[var(--space-4)] py-[var(--space-2)] transition-colors focus-within:border-[var(--color-border-strong)] motion-reduce:transition-none">
          <Search
            className="size-[var(--icon-size-lg)] shrink-0 text-[var(--color-ink-tertiary)] transition-colors group-focus-within:text-[var(--color-brand)] motion-reduce:transition-none"
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            id={SEARCH_INPUT_ID}
            className="h-[var(--control-size-lg)] min-w-0 flex-1 bg-transparent text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)] text-[var(--color-ink-primary)] caret-[var(--color-brand)] outline-none placeholder:text-[var(--color-ink-tertiary)]"
            placeholder="搜索命令"
            aria-label="搜索命令"
            role="combobox"
            aria-expanded="true"
            aria-controls={LISTBOX_ID}
            aria-activedescendant={
              activeItem ? optionId(activeItem) : undefined
            }
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={handleKeyDown}
          />
          {query ? (
            <button
              type="button"
              className={buttonClassName({ variant: "ghost", size: "icon" })}
              aria-label="清除搜索"
              tabIndex={-1}
              onClick={() => {
                setQuery("");
                inputRef.current?.focus();
              }}
            >
              <X className="size-[var(--icon-size-md)]" aria-hidden="true" />
            </button>
          ) : null}
        </div>

        <div
          id={LISTBOX_ID}
          role="listbox"
          className="min-h-0 flex-1 overflow-y-auto p-[var(--space-2)]"
        >
          {filteredItems.length === 0 ? (
            <p className="px-[var(--space-4)] py-[var(--space-8)] text-center text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)] text-[var(--color-ink-secondary)]">
              没有匹配的命令
            </p>
          ) : (
            COMMAND_MENU_GROUP_ORDER.map((group) => {
              const groupItems = filteredItems.filter(
                (item) => item.group === group,
              );
              if (groupItems.length === 0) return null;
              return (
                <section key={group} className="py-[var(--space-1)]">
                  <h2 className="px-[var(--space-3)] py-[var(--space-2)] text-[length:var(--font-size-ui-label)] leading-[var(--line-height-ui-label)] font-semibold text-[var(--color-ink-tertiary)]">
                    {COMMAND_MENU_GROUP_LABELS[group]}
                  </h2>
                  {groupItems.map((item) => {
                    const index = filteredItems.indexOf(item);
                    const active = index === boundedActiveIndex;
                    return (
                      <button
                        key={item.id}
                        ref={(node) => {
                          if (node) optionRefs.current.set(item.id, node);
                          else optionRefs.current.delete(item.id);
                        }}
                        id={optionId(item)}
                        type="button"
                        role="option"
                        aria-selected={active}
                        tabIndex={-1}
                        className={cn(
                          "flex w-full items-center gap-[var(--space-3)] rounded-[var(--radius-md)] px-[var(--space-3)] py-[var(--space-3)] text-left text-[length:var(--font-size-ui-body)] leading-[var(--line-height-ui-body)]",
                          active
                            ? "bg-[var(--color-brand-muted)] text-[var(--color-ink-primary)]"
                            : "text-[var(--color-ink-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-ink-primary)]",
                        )}
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => runItem(item)}
                      >
                        <span
                          className="flex size-[var(--control-size-md)] shrink-0 items-center justify-center"
                          aria-hidden="true"
                        >
                          {item.icon}
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block font-medium">
                            {item.title}
                          </span>
                          <span className="block truncate text-[length:var(--font-size-ui-label)] leading-[var(--line-height-ui-label)] text-[var(--color-ink-tertiary)]">
                            {item.description}
                          </span>
                        </span>
                        {item.status ? (
                          <span
                            className={`shrink-0 inline-block size-1.5 rounded-full ${
                              item.status === "running"
                                ? "bg-[var(--color-info)] animate-pulse"
                                : item.status === "waiting"
                                  ? "bg-[var(--color-warning)]"
                                  : item.status === "error"
                                    ? "bg-[var(--color-error)]"
                                    : "workspace-status-dot--idle"
                            }`}
                            aria-hidden="true"
                          />
                        ) : null}
                      </button>
                    );
                  })}
                </section>
              );
            })
          )}
        </div>
        <p className="border-t border-[var(--color-border)] px-[var(--space-4)] py-[var(--space-2)] text-[length:var(--font-size-ui-label)] leading-[var(--line-height-ui-label)] text-[var(--color-ink-tertiary)]">
          使用方向键选择，Enter 执行，Esc 关闭
        </p>
      </div>
    </div>,
    document.body,
  );
}
