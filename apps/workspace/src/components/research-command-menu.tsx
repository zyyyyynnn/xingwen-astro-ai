import { Command } from "cmdk";
import { useEffect } from "react";

export interface CommandItem {
  readonly id: string;
  readonly label: string;
  readonly onSelect: () => void;
  readonly keywords?: string;
}

export interface CommandGroup {
  readonly label: string;
  readonly items: readonly CommandItem[];
}

export interface ResearchCommandMenuProps {
  readonly open: boolean;
  readonly onOpenChange: (open: boolean) => void;
  readonly groups: readonly CommandGroup[];
}

/** Command Palette powered by cmdk — grouped commands with keyboard navigation. */
export function ResearchCommandMenu({
  open,
  onOpenChange,
  groups,
}: ResearchCommandMenuProps) {
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onOpenChange(false);
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onOpenChange]);

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "k") {
        event.preventDefault();
        onOpenChange(!open);
      }
    };
    document.addEventListener("keydown", handleShortcut);
    return () => document.removeEventListener("keydown", handleShortcut);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      className="research-command-menu__overlay"
      onClick={() => onOpenChange(false)}
    >
      <div
        className="research-command-menu__dialog"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="命令面板"
      >
        <Command label="命令面板">
          <Command.Input
            className="research-command-menu__input"
            placeholder="搜索命令或对象…"
            autoFocus
          />
          <Command.List className="research-command-menu__list">
            <Command.Empty className="research-command-menu__empty">
              无匹配结果
            </Command.Empty>
            {groups.map((group) => (
              <Command.Group
                key={group.label}
                heading={group.label}
                className="research-command-menu__group"
              >
                {group.items.map((item) => (
                  <Command.Item
                    key={item.id}
                    value={`${item.label} ${item.keywords ?? ""}`}
                    onSelect={() => {
                      item.onSelect();
                      onOpenChange(false);
                    }}
                    className="research-command-menu__item"
                  >
                    {item.label}
                  </Command.Item>
                ))}
              </Command.Group>
            ))}
          </Command.List>
        </Command>
      </div>
    </div>
  );
}
