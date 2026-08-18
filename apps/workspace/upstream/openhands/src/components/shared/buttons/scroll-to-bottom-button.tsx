import { Button } from "@xingwen/ui";
import { ChevronDown } from "@xingwen/ui/icons";

export function ScrollToBottomButton({
  onClick,
  newCount = 0,
}: {
  readonly onClick: () => void;
  /** Main stream items published while the reader stayed scrolled up. */
  readonly newCount?: number;
}) {
  const label =
    newCount > 0 ? `${newCount} 条新进展，滚动到最新` : "滚动到最新研究进展";
  return (
    <Button
      variant="secondary"
      size={newCount > 0 ? "default" : "icon"}
      onClick={onClick}
      data-testid="scroll-to-bottom"
      aria-label={label}
      className="rounded-[var(--oh-radius-pill)] text-[var(--oh-muted)]"
    >
      <ChevronDown
        className="size-[var(--oh-icon-size-sm)]"
        aria-hidden="true"
      />
      {newCount > 0 ? (
        <span className="px-1 text-xs" data-testid="new-progress-count">
          ↓ {newCount} 条新进展
        </span>
      ) : null}
    </Button>
  );
}
