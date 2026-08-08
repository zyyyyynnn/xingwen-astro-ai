import type React from "react";

import { cn } from "../../../../utils/utils";

interface ChatInputGripProps {
  readonly gripRef: React.RefObject<HTMLDivElement | null>;
  readonly isGripVisible: boolean;
  readonly isGripDragging: boolean;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly handleTopEdgeClick: (event: React.MouseEvent) => void;
  readonly handleGripMouseDown: (event: React.MouseEvent) => void;
  readonly handleGripKeyDown: (event: React.KeyboardEvent) => void;
}

export function ChatInputGrip({
  gripRef,
  isGripVisible,
  isGripDragging,
  value,
  min,
  max,
  handleTopEdgeClick,
  handleGripMouseDown,
  handleGripKeyDown,
}: ChatInputGripProps) {
  return (
    <div
      ref={gripRef}
      className="group/grip absolute left-1/2 top-0 z-20 h-3 w-12 -translate-x-1/2 -translate-y-1/2 cursor-ns-resize outline-none"
      role="separator"
      aria-label="调整指令输入区高度"
      aria-orientation="horizontal"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      tabIndex={0}
      onClick={handleTopEdgeClick}
      onMouseDown={handleGripMouseDown}
      onKeyDown={handleGripKeyDown}
    >
      <span
        className={cn(
          "pointer-events-none absolute left-1/2 top-1/2 h-1 w-8 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--oh-border-strong)] transition-opacity group-focus-visible/grip:opacity-100 motion-reduce:transition-none",
          isGripVisible || isGripDragging ? "opacity-100" : "opacity-0",
        )}
        aria-hidden="true"
      />
    </div>
  );
}
