import { Button } from "@xingwen/ui";
import { ChevronDown } from "@xingwen/ui/icons";

export function ScrollToBottomButton({ onClick }: { onClick: () => void }) {
  return (
    <Button
      variant="secondary"
      size="icon"
      onClick={onClick}
      data-testid="scroll-to-bottom"
      aria-label="滚动到最新研究进展"
      className="rounded-[var(--oh-radius-pill)] text-[var(--oh-muted)]"
    >
      <ChevronDown
        className="size-[var(--oh-icon-size-sm)]"
        aria-hidden="true"
      />
    </Button>
  );
}
