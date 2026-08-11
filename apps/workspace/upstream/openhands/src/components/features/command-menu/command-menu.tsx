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

interface CommandMenuProps {
  readonly onNewResearch: () => void;
}

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

export function CommandMenu({ onNewResearch }: CommandMenuProps) {
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
        newResearch: onNewResearch,
        toggleSidebar: () => useSidebarStore.getState().toggleCollapsed(),
      }),
    [onNewResearch],
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
      className="fixed inset-0 z-[var(--oh-layer-command-menu)] flex items-start justify-center bg-[var(--oh-overlay)] px-[var(--oh-space-6)] pt-[var(--oh-command-menu-viewport-offset)]"
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
      <div className="relative flex max-h-[var(--oh-command-menu-max-block-size)] w-full max-w-[var(--oh-command-menu-max-inline-size)] flex-col overflow-hidden rounded-[var(--oh-radius-lg)] border border-[var(--oh-border-strong)] bg-[var(--oh-surface)] shadow-[var(--oh-shadow-modal)]">
        <div className="group flex items-center gap-[var(--oh-space-3)] border-b border-[var(--oh-border)] px-[var(--oh-space-4)] py-[var(--oh-space-2)] transition-colors focus-within:border-[var(--oh-border-strong)] motion-reduce:transition-none">
          <Search
            className="size-[var(--oh-icon-size-lg)] shrink-0 text-[var(--oh-text-dim)] transition-colors group-focus-within:text-[var(--oh-accent)] motion-reduce:transition-none"
            aria-hidden="true"
          />
          <input
            ref={inputRef}
            id={SEARCH_INPUT_ID}
            className="h-[var(--oh-control-size-lg)] min-w-0 flex-1 bg-transparent text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-text)] caret-[var(--oh-accent)] outline-none placeholder:text-[var(--oh-text-dim)]"
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
              <X className="size-[var(--oh-icon-size-md)]" aria-hidden="true" />
            </button>
          ) : null}
        </div>

        <div
          id={LISTBOX_ID}
          role="listbox"
          className="min-h-0 flex-1 overflow-y-auto p-[var(--oh-space-2)]"
        >
          {filteredItems.length === 0 ? (
            <p className="px-[var(--oh-space-4)] py-[var(--oh-space-8)] text-center text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)] text-[var(--oh-muted)]">
              没有匹配的命令
            </p>
          ) : (
            COMMAND_MENU_GROUP_ORDER.map((group) => {
              const groupItems = filteredItems.filter(
                (item) => item.group === group,
              );
              if (groupItems.length === 0) return null;
              return (
                <section key={group} className="py-[var(--oh-space-1)]">
                  <h2 className="px-[var(--oh-space-3)] py-[var(--oh-space-2)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] font-semibold text-[var(--oh-text-dim)]">
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
                          "flex w-full items-center gap-[var(--oh-space-3)] rounded-[var(--oh-radius-md)] px-[var(--oh-space-3)] py-[var(--oh-space-3)] text-left text-[length:var(--oh-font-size-body)] leading-[var(--oh-line-height-body)]",
                          active
                            ? "bg-[var(--oh-accent-muted)] text-[var(--oh-text)]"
                            : "text-[var(--oh-muted)] hover:bg-[var(--oh-surface-raised)] hover:text-[var(--oh-text)]",
                        )}
                        onMouseEnter={() => setActiveIndex(index)}
                        onClick={() => runItem(item)}
                      >
                        <span
                          className="flex size-[var(--oh-control-size-md)] shrink-0 items-center justify-center"
                          aria-hidden="true"
                        >
                          {item.icon}
                        </span>
                        <span className="min-w-0">
                          <span className="block font-medium">
                            {item.title}
                          </span>
                          <span className="block truncate text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
                            {item.description}
                          </span>
                        </span>
                      </button>
                    );
                  })}
                </section>
              );
            })
          )}
        </div>
        <p className="border-t border-[var(--oh-border)] px-[var(--oh-space-4)] py-[var(--oh-space-2)] text-[length:var(--oh-font-size-label)] leading-[var(--oh-line-height-label)] text-[var(--oh-text-dim)]">
          使用方向键选择，Enter 执行，Esc 关闭
        </p>
      </div>
    </div>,
    document.body,
  );
}
