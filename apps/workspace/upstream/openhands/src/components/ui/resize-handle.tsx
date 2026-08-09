import React from "react";

import { cn } from "../../utils/utils";

interface ResizeHandleProps {
  readonly onMouseDown: (event: React.MouseEvent) => void;
  readonly onKeyboardResize: (direction: -1 | 1) => void;
  readonly value: number;
  readonly min: number;
  readonly max: number;
  readonly className?: string;
  readonly isDragging?: boolean;
}

export function ResizeHandle({
  onMouseDown,
  onKeyboardResize,
  value,
  min,
  max,
  className,
  isDragging = false,
}: ResizeHandleProps) {
  const [isHovering, setIsHovering] = React.useState(false);
  const active = isDragging || isHovering;

  return (
    <div
      className={cn(
        "group relative z-[var(--oh-layer-resize-handle)] w-0 shrink-0 self-stretch outline-none",
        className,
      )}
      role="separator"
      aria-label="调整任务与活动面板宽度"
      aria-orientation="vertical"
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={Math.round(value)}
      tabIndex={0}
      onMouseDown={onMouseDown}
      onMouseEnter={() => setIsHovering(true)}
      onMouseLeave={() => setIsHovering(false)}
      onKeyDown={(event) => {
        if (event.key === "ArrowLeft") {
          event.preventDefault();
          onKeyboardResize(-1);
        } else if (event.key === "ArrowRight") {
          event.preventDefault();
          onKeyboardResize(1);
        }
      }}
    >
      <span className="absolute inset-y-0 left-1/2 w-[var(--oh-space-3)] -translate-x-1/2 cursor-ew-resize" />
      <span
        className={cn(
          "pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors duration-[var(--oh-motion-navigation)] motion-reduce:transition-none",
          active ? "bg-[var(--oh-accent)]" : "bg-[var(--oh-border)]",
        )}
        aria-hidden="true"
      />
    </div>
  );
}
