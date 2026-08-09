import { Square } from "lucide-react";

interface ChatStopButtonProps {
  readonly handleStop: () => void;
}

export function ChatStopButton({ handleStop }: ChatStopButtonProps) {
  return (
    <button
      type="button"
      onClick={handleStop}
      data-testid="stop-button"
      aria-label="取消任务"
      className="flex size-[var(--oh-control-size-sm)] items-center justify-center rounded-[var(--oh-radius-pill)] border border-[var(--oh-border-strong)] text-[var(--oh-text)] hover:bg-[var(--oh-surface-raised)]"
    >
      <Square
        className="size-[var(--oh-icon-size-xs)]"
        fill="currentColor"
        aria-hidden="true"
      />
    </button>
  );
}
