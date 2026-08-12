import React from "react";

import { cn } from "../../../utils/utils";

const USER_MESSAGE_MAX_LINES = 5;
const USER_MESSAGE_LENGTH_THRESHOLD = 360;
const USER_MESSAGE_LINE_HEIGHT_PX = 24;

/** OpenHands long-user-message collapse mechanic over public plain text. */
export function UserMessageBody({
  message,
  expanded,
  onTruncatableChange,
}: {
  readonly message: string;
  readonly expanded: boolean;
  readonly onTruncatableChange: (truncatable: boolean) => void;
}) {
  const contentRef = React.useRef<HTMLDivElement>(null);
  const [truncatable, setTruncatable] = React.useState(false);

  React.useEffect(
    () => onTruncatableChange(truncatable),
    [onTruncatableChange, truncatable],
  );

  React.useLayoutEffect(() => {
    const content = contentRef.current;
    if (!content || expanded) {
      setTruncatable(false);
      return undefined;
    }
    const measure = () => {
      const measured = Number.parseFloat(getComputedStyle(content).lineHeight);
      const lineHeight =
        Number.isFinite(measured) && measured > 0
          ? measured
          : USER_MESSAGE_LINE_HEIGHT_PX;
      setTruncatable(
        content.scrollHeight > USER_MESSAGE_MAX_LINES * lineHeight + 1 ||
          (message.match(/\n/g) ?? []).length >= USER_MESSAGE_MAX_LINES ||
          message.trim().length > USER_MESSAGE_LENGTH_THRESHOLD,
      );
    };
    measure();
    if (typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(measure);
    observer.observe(content);
    return () => observer.disconnect();
  }, [expanded, message]);

  const collapsed = truncatable && !expanded;
  return (
    <div className="relative min-w-0">
      <div
        ref={contentRef}
        className={cn(
          "min-w-0 whitespace-pre-wrap text-sm leading-6 [word-break:break-word]",
          collapsed && "line-clamp-5",
        )}
      >
        {message}
      </div>
      {collapsed ? (
        <>
          <div
            aria-hidden="true"
            className="pointer-events-none absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-[var(--oh-surface-muted)] to-transparent"
          />
          <span className="pointer-events-none absolute bottom-0.5 left-1/2 z-10 -translate-x-1/2 rounded-[var(--oh-radius-pill)] bg-[var(--oh-surface-raised)] px-2.5 py-0.5 text-xs text-[var(--oh-text)] shadow-sm">
            展开
          </span>
        </>
      ) : null}
    </div>
  );
}
